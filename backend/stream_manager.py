import cv2
import threading
import queue
import time
import asyncio
from aiortc import VideoStreamTrack
from av import VideoFrame

import sys
import os

from models.ppe_service import PPEService

# Initialize AI Service globally as a Singleton so we don't reload the Heavy ONNX model uniquely per camera thread
PPE_SERVICE_SINGLETON = PPEService(r"d:\Antigravity\DT-Project\models\PPE_detection.onnx")

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
        self.current_inference_frame = None
        self.latest_detections = []
        
        # Start isolated ingestion thread
        self.thread = threading.Thread(target=self._ingest_video, daemon=True)
        self.thread.start()
        
        # Start DECOUPLED AI inference thread so WebRTC doesn't stall
        self.ai_thread = threading.Thread(target=self._ai_inference_loop, daemon=True)
        self.ai_thread.start()
        
    def _ingest_video(self):
        """Background daemon thread to fetch video continuously."""
        print(f"[Thread-Start] Ingesting video from: {self.camera_url}")
        
        # FIX FOR NGROK & SSL ISSUES:
        # 1. 'tls_verify;0' bypasses strict SSL handshake errors on Windows.
        # 2. 'headers;ngrok-skip-browser-warning: true' bypasses the free ngrok HTML warning tier.
        import os
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "tls_verify;0|headers;ngrok-skip-browser-warning: true"
        
        # Auto-reconnection loop keeps attempting to reconnect if the stream drops
        while not self.stopped:
            cap = cv2.VideoCapture(self.camera_url, cv2.CAP_FFMPEG)
            
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
                
                # Make a snapshot locally for the detached AI loop to work on 
                self.current_inference_frame = frame_rgb.copy()
                
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
        """Detached Daemon thread constantly churning AI frames seamlessly in the background!"""
        print(f"[AI-Thread] GPU background execution started for {self.camera_url}")
        while not self.stopped:
            if self.current_inference_frame is not None:
                # ── START AI CASCADE OPTIMIZATION ──
                # 1. Grab snapshot and resize purely for AI speed
                frame_snap = self.current_inference_frame.copy()
                h, w = frame_snap.shape[:2]
                target_w, target_h = 1280, 720
                resized_frame = cv2.resize(frame_snap, (target_w, target_h))
                
                # 2. Synchronous GPU execution! (But it's detached, so video stream won't pause)
                detections = PPE_SERVICE_SINGLETON.detect_ppe(resized_frame)
                
                # 3. Upscale bounding coordinates heavily
                if detections:
                    scale_x = w / target_w
                    scale_y = h / target_h
                    for det in detections:
                        x1, y1, x2, y2 = det.bbox
                        det.bbox = (int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y))
                
                # Update global bindings over the class securely
                self.latest_detections = detections
                
                # Minor GPU relaxer
                time.sleep(0.01)
            else:
                time.sleep(0.05)

    async def recv(self):
        """Required aiortc method to retrieve the next WebRTC video frame."""
        # Await a fresh frame from the ingestion queue, yield control back to event loop if empty
        while self.Q.empty() and not self.stopped:
            await asyncio.sleep(0.01) 
            
        if self.stopped:
            return None
            
        try:
            frame_rgb = self.Q.get_nowait()
            
            # Draw any available decoupled AI boxes instantaneously without processing lag
            if self.latest_detections:
                PPE_SERVICE_SINGLETON.draw_ppe_boxes(frame_rgb, self.latest_detections)
            
            # Create a PyAV VideoFrame required by aiortc
            pts, time_base = await self.next_timestamp()
            video_frame = VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            video_frame.pts = pts
            video_frame.time_base = time_base
            return video_frame
            
        except queue.Empty:
            # Recursively wait via asyncio if race condition caused emptiness
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

    def get_or_create_track(self, camera_url: str) -> NetworkCameraTrack:
        # Check if we already have an ongoing thread/track for this physical camera
        if camera_url in self.active_tracks:
            print(f"[StreamManager] Reusing existing ingestion track for {camera_url}")
            return self.active_tracks[camera_url]
            
        # Spawn NEW isolated background thread and queue
        print(f"[StreamManager] Provisioning NEW Track & Thread for {camera_url}")
        track = NetworkCameraTrack(camera_url)
        self.active_tracks[camera_url] = track
        return track
        
    def close_track(self, camera_url: str):
        if camera_url in self.active_tracks:
            track = self.active_tracks.pop(camera_url)
            track.stop()

# Singleton instance exported for main.py
stream_factory = StreamManager()
