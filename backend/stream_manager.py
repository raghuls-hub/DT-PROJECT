import cv2
import threading
import queue
import time
import asyncio
import fractions
from aiortc import VideoStreamTrack
from av import VideoFrame

import sys
import os

from models.ppe_service import PPEService
from models.fire_service import FireService
from models.fall_service import FallService

# Global Lock to prevent multiple threads from competing for 'os.environ'
# when some cameras are local (no headers) and others are remote (ngrok bypass headers)
ENV_LOCK = threading.Lock()

# Define root directory relative to this file
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# INITIALIZING PPE MODEL
PPE_SERVICE_SINGLETON = PPEService(os.path.join(ROOT_DIR, "models", "basic-model.onnx"))

# UNFREEZING FIRE MODEL
FIRE_SERVICE_SINGLETON = FireService(os.path.join(ROOT_DIR, "models", "fire_detection.onnx"))

# INITIALIZING FALL MODEL
FALL_SERVICE_SINGLETON = FallService(os.path.join(ROOT_DIR, "models", "fall_detection.onnx"))

class NetworkCameraTrack(VideoStreamTrack):
    """
    An isolated WebRTC VideoStreamTrack that consumes an external camera API.
    Runs its own background thread and `queue.Queue(maxsize=1)` for aggressive frame dropping.
    """
    def __init__(self, camera_url: str):
        super().__init__()
        self.camera_url = camera_url
        
        # Maxsize=1 is CRITICAL for low-latency. It prevents buffering old frames.
        self.Q = queue.Queue(maxsize=1)
        self.stopped = False
        self.current_inference_frame = None   # BGR frame for AI models
        self.latest_raw_ppe_detections = []
        self.latest_ppe_statuses = []
        self.latest_fire_detections = []
        self.latest_fall_detections = []
        self.monitored_ppe = []  # Selection from frontend
        self.ai_frame_counter = 0

        # Timestamping and playback state
        self.frame_count = 0
        self.fps = 30.0

        # Temporal alert states
        self.fire_start_time = None
        self.ppe_violation_start_time = None
        self.confirmed_fire = False
        self.confirmed_ppe = False
        self.confirmed_fall = False

        # Dismissal delay state
        self.fire_last_seen = 0
        self.fall_last_seen = 0
        self.ppe_violation_last_seen = 0
        self.fall_frame_acc = 0
        
        # Start isolated ingestion thread
        self.thread = threading.Thread(target=self._ingest_video, daemon=True)
        self.thread.start()
        
        # Start DECOUPLED AI inference thread so WebRTC doesn't stall
        self.ai_thread = threading.Thread(target=self._ai_inference_loop, daemon=True)
        self.ai_thread.start()
        
    def _ingest_video(self):
        """Background daemon thread to fetch video continuously."""
        print(f"[Thread-Start] Ingesting video from: {self.camera_url}")
        
        # ── LOCAL PATH RESOLUTION ──
        # Resolves Flask URLs back to direct files to bypass HTTP handshake issues on Windows
        final_url = self.camera_url
        is_local_file = False
        
        if "5000/stream/" in self.camera_url:
            filename = self.camera_url.split("/stream/")[-1].replace("%20", " ")
            potential_file = os.path.join(ROOT_DIR, "videos", filename)
            if os.path.exists(potential_file):
                print(f"[StreamManager] URL Resolved to direct path: {potential_file}")
                final_url = potential_file
                is_local_file = True

        # TWO-WAY ACCEPTANCE LOGIC (Local vs IP Camera/Ngrok)
        is_local_conn = any(x in self.camera_url for x in ["localhost", "127.0.0.1", "::1"])
        
        # Auto-reconnection loop keeps attempting to reconnect if the stream drops
        while not self.stopped:
            # 1. Prepare environment for this specific connection
            with ENV_LOCK:
                if is_local_conn or is_local_file:
                    if "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
                        del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
                else:
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "tls_verify;0|headers;ngrok-skip-browser-warning: true"
                
                # 2. Use CAP_FFMPEG only for network URLs (files work natively)
                if is_local_file:
                    cap = cv2.VideoCapture(final_url)
                else:
                    cap = cv2.VideoCapture(final_url, cv2.CAP_FFMPEG)
            
            # 3. Fallback Mechanism
            if not cap.isOpened():
                print(f"[Warning] Backend open failed for {final_url}. Attempting final OS fallback...")
                cap = cv2.VideoCapture(final_url)
            
            # Force high-definition capture (crucial if using physical webcams or variable RTSP streams)
            # NOTE: Commented out natively because forcing hardware resolution on basic HTTP .mp4 streams 
            # instantly corrupts the FFMPEG byte-context causing endless frame drops!
            # cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            
            if not cap.isOpened():
                print(f"[Error] Cannot open camera: {self.camera_url}. Retrying in 5s...")
                time.sleep(5)
                continue
                
            # Extract FPS to limit playback speed for file-streams
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not fps or fps <= 0 or fps > 120:
                fps = 30.0 # Fallback FPS
            delay = 1.0 / fps
                
            while not self.stopped:
                loop_start = time.time()
                
                ret, frame = cap.read()
                if not ret:
                    print(f"[Warning] Frame drop or connection lost for: {self.camera_url}")
                    break # Break inner loop to trigger cap.release() and reconnect
                
                # Convert BGR (OpenCV) to RGB (WebRTC default)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # ── CRITICAL ──
                # Store the ORIGINAL BGR frame for AI inference.
                # YOLO/ONNX models expect BGR (OpenCV native), NOT RGB.
                # The RGB frame is only for the WebRTC pipeline.
                self.current_inference_frame = frame.copy()  # BGR
                
                # Aggressive dropping mechanism (maxsize=1)
                try:
                    self.Q.put_nowait(frame_rgb)
                except queue.Full:
                    try:
                        self.Q.get_nowait() # Discard oldest frame to prevent lagging
                        self.Q.put_nowait(frame_rgb) # Insert latest frame
                    except queue.Empty:
                        pass
                        
                # Sleep to enforce real-time playback speed
                elapsed = time.time() - loop_start
                if elapsed < delay:
                    time.sleep(delay - elapsed)
                        
            cap.release()
            
    def _ai_inference_loop(self):
        """Detached daemon thread constantly churning AI frames seamlessly in the background!"""
        print(f"[AI-Thread] CPU background execution started for {self.camera_url}")
        
        processed_count = 0
        
        while not self.stopped:
            if self.current_inference_frame is not None:
                processed_count += 1
                
                # OPTIMIZATION: Run AI on 1 out of every 3 captured frames.
                if processed_count % 3 != 1:
                    time.sleep(0.01)
                    continue

                frame_snap = self.current_inference_frame.copy()
                
                fall_detections = FALL_SERVICE_SINGLETON.detect_fall(frame_snap)
                self.latest_fall_detections = fall_detections

                fire_detections = FIRE_SERVICE_SINGLETON.detect_fire(frame_snap)
                self.latest_fire_detections = fire_detections

                raw_ppe = PPE_SERVICE_SINGLETON.detect_ppe(frame_snap)
                ppe_statuses = PPE_SERVICE_SINGLETON.process_person_logic(raw_ppe, self.monitored_ppe)
                self.latest_raw_ppe_detections = raw_ppe
                self.latest_ppe_statuses = ppe_statuses

                now = time.time()

                if FIRE_SERVICE_SINGLETON.has_fire(fire_detections):
                    self.fire_last_seen = now
                    if self.fire_start_time is None:
                        self.fire_start_time = now
                    elif now - self.fire_start_time >= 4.0:
                        self.confirmed_fire = True
                else:
                    self.fire_start_time = None
                    if now - self.fire_last_seen > 3.0:
                        self.confirmed_fire = False

                has_fallen = any(d.class_name.lower() == "fallen" for d in fall_detections)
                if has_fallen:
                    self.fall_last_seen = now
                    self.fall_frame_acc += 1
                    if self.fall_frame_acc >= 10:
                        self.confirmed_fall = True
                else:
                    self.fall_frame_acc = 0
                    if now - self.fall_last_seen > 3.0:
                        self.confirmed_fall = False

                has_violation = any(s.violations for s in ppe_statuses)
                if has_violation:
                    self.ppe_violation_last_seen = now
                    if self.ppe_violation_start_time is None:
                        self.ppe_violation_start_time = now
                    elif now - self.ppe_violation_start_time >= 5.0:
                        self.confirmed_ppe = True
                else:
                    self.ppe_violation_start_time = None
                    if now - self.ppe_violation_last_seen > 3.0:
                        self.confirmed_ppe = False
                
                if self.ai_frame_counter > 15000:
                    self.ai_frame_counter = 0
                
                time.sleep(0.01)
            else:
                time.sleep(0.05)

    async def recv(self):
        """Required aiortc method to retrieve the next WebRTC video frame."""
        while self.Q.empty() and not self.stopped:
            await asyncio.sleep(0.01)

        if self.stopped:
            return None

        try:
            frame_rgb = self.Q.get_nowait()

            if self.latest_fall_detections:
                FALL_SERVICE_SINGLETON.draw_fall_boxes(frame_rgb, self.latest_fall_detections, self.confirmed_fall)

            FIRE_SERVICE_SINGLETON.annotate_frame(frame_rgb, self.latest_fire_detections, self.confirmed_fire)

            PPE_SERVICE_SINGLETON.draw_ppe_results(
                frame_rgb,
                self.latest_ppe_statuses,
                self.latest_raw_ppe_detections,
                self.confirmed_ppe,
            )

            self.frame_count += 1
            pts = int(self.frame_count * (90000 / self.fps))
            time_base = fractions.Fraction(1, 90000)
            video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            video_frame.pts = pts
            video_frame.time_base = time_base
            return video_frame

        except queue.Empty:
            await asyncio.sleep(0.01)
            return await self.recv()

    def stop(self):
        """Tears down the isolated stream."""
        self.stopped = True
        self.thread.join(timeout=1.0)
        print(f"[Thread-Stop] Camera isolated thread terminated: {self.camera_url}")


class StreamManager:
    """
    Maintains a dictionary of active streams to avoid duplicating threads
    if multiple users request the exact same target URL.
    """
    def __init__(self):
        self.active_tracks = {}

    def get_or_create_track(self, camera_url: str, monitored_ppe: list = None) -> NetworkCameraTrack:
        if camera_url in self.active_tracks:
            track = self.active_tracks[camera_url]
            if track.stopped:
                print(f"[StreamManager] Existing track has already stopped for {camera_url}. Creating a new one.")
                self.active_tracks.pop(camera_url, None)
            else:
                print(f"[StreamManager] Reusing existing track for {camera_url}")
                if monitored_ppe is not None:
                    track.monitored_ppe = monitored_ppe
                return track
            
        print(f"[StreamManager] Provisioning NEW Track for {camera_url}")
        track = NetworkCameraTrack(camera_url)
        if monitored_ppe is not None:
            track.monitored_ppe = monitored_ppe
        self.active_tracks[camera_url] = track
        return track
        
    def close_track(self, camera_url: str):
        if camera_url in self.active_tracks:
            track = self.active_tracks.pop(camera_url)
            track.stop()

# Singleton instance exported for main.py
stream_factory = StreamManager()
