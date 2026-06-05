import cv2
import threading
import queue
import time
import asyncio
import fractions
import numpy as np
import requests
from typing import List
from aiortc import VideoStreamTrack
from av import VideoFrame

import numpy as np
from typing import List

import sys
import os

from models.ppe_service import PPEService
from models.fire_service import FireService
from models.fall_service import FallService
from config import NOTIFY_CONSECUTIVE_THRESHOLD, NOTIFY_COOLDOWN_SECONDS

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
    def __init__(self, camera_url: str, endpoint: str = None, camera_name: str = None):
        super().__init__()
        self.camera_url = camera_url
        self.camera_name = camera_name or camera_url  # Human-readable name for alerts
        self.endpoint = endpoint  # Ntfy.sh endpoint for alerts
        self.last_alert_time = 0  # Track last alert time for rate limiting
        
        # Maxsize=1 is CRITICAL for low-latency. It prevents buffering old frames.
        self.Q = queue.Queue(maxsize=1)
        self.stopped = False
        self.cap = None
        self.current_inference_frame = None   # BGR frame for AI models
        self.latest_raw_ppe_detections = []
        self.latest_ppe_statuses = []
        self.latest_fire_detections = []
        self.latest_fall_detections = []
        self.monitored_ppe = []  # Selection from frontend
        self.ai_frame_counter = 0

        # Lightweight person trackers for smooth box updates between expensive detections
        # Map: tracker_id -> {"tracker": cv2.Tracker, "bbox": (x,y,w,h), "last_seen": timestamp}
        self.person_trackers = {}
        self._next_tracker_id = 1

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
        # Per-violation consecutive counters and last-sent timestamps (per video/track)
        self.alert_counters = {
            'fire': 0,
            'ppe': 0,
            'fall': 0,
        }
        self.alert_last_sent = {
            'fire': 0.0,
            'ppe': 0.0,
            'fall': 0.0,
        }
        
        # Start isolated ingestion thread
        self.thread = threading.Thread(target=self._ingest_video, daemon=True)
        self.thread.start()
        
        # Start DECOUPLED AI inference thread so WebRTC doesn't stall
        self.ai_thread = threading.Thread(target=self._ai_inference_loop, daemon=True)
        self.ai_thread.start()
    
    @property
    def latest_frame(self):
        """Get the latest BGR frame for PPE verification purposes."""
        return self.current_inference_frame
        
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
                # expose capture so stop() can release it promptly
                self.cap = cap
            
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
            self.cap = None
            
    def _ai_inference_loop(self):
        """Detached daemon thread constantly churning AI frames seamlessly in the background!"""
        print(f"[AI-Thread] CPU background execution started for {self.camera_url}")
        
        processed_count = 0
        
        while not self.stopped:
            if self.current_inference_frame is not None:
                processed_count += 1
                
                frame_snap = self.current_inference_frame.copy()
                
                # Run PPE detection on every 2nd frame for balanced performance and tracking
                if processed_count % 2 == 1:
                    raw_ppe = PPE_SERVICE_SINGLETON.detect_ppe(frame_snap)
                    ppe_statuses = PPE_SERVICE_SINGLETON.process_person_logic(raw_ppe, self.monitored_ppe)
                    self.latest_raw_ppe_detections = raw_ppe
                    self.latest_ppe_statuses = ppe_statuses

                    # Update/initialize lightweight trackers for detected persons
                    person_dets = [d for d in raw_ppe if d.class_name == "Person"]
                    self._sync_person_trackers(person_dets, frame_snap)
                else:
                    # Between detection runs, update trackers to provide smooth bbox updates
                    self._update_person_trackers(frame_snap)
                
                # Run fall and fire detection on 1 out of every 3 frames for performance
                if processed_count % 3 == 1:
                    fall_detections = FALL_SERVICE_SINGLETON.detect_fall(frame_snap)
                    self.latest_fall_detections = fall_detections

                    fire_detections = FIRE_SERVICE_SINGLETON.detect_fire(frame_snap)
                    self.latest_fire_detections = fire_detections

                now = time.time()

                # New per-violation consecutive counters and cooldown logic
                # FIRE
                has_fire = FIRE_SERVICE_SINGLETON.has_fire(self.latest_fire_detections)
                if has_fire:
                    self.alert_counters['fire'] += 1
                else:
                    self.alert_counters['fire'] = 0

                if self.alert_counters['fire'] >= NOTIFY_CONSECUTIVE_THRESHOLD:
                    # Check cooldown for this violation type
                    if now - self.alert_last_sent['fire'] > NOTIFY_COOLDOWN_SECONDS:
                        self._send_alert_notification("FIRE DETECTED - EVACUATE IMMEDIATELY", "fire")
                        self.alert_last_sent['fire'] = now

                # FALL
                has_fallen = any(d.class_name.lower() == "fallen" for d in self.latest_fall_detections)
                if has_fallen:
                    self.alert_counters['fall'] += 1
                else:
                    self.alert_counters['fall'] = 0

                if self.alert_counters['fall'] >= NOTIFY_CONSECUTIVE_THRESHOLD:
                    if now - self.alert_last_sent['fall'] > NOTIFY_COOLDOWN_SECONDS:
                        self._send_alert_notification("FALL DETECTED - ASSISTANCE REQUIRED", "fall")
                        self.alert_last_sent['fall'] = now

                # PPE violations (person-centric)
                has_violation = any(s.violations for s in ppe_statuses)
                if has_violation:
                    self.alert_counters['ppe'] += 1
                else:
                    self.alert_counters['ppe'] = 0

                if self.alert_counters['ppe'] >= NOTIFY_CONSECUTIVE_THRESHOLD:
                    if now - self.alert_last_sent['ppe'] > NOTIFY_COOLDOWN_SECONDS:
                        self._send_alert_notification("PPE VIOLATION DETECTED - SAFETY GEAR MISSING", "ppe")
                        self.alert_last_sent['ppe'] = now
                
                if self.ai_frame_counter > 15000:
                    self.ai_frame_counter = 0
                
                time.sleep(0.01)
            else:
                time.sleep(0.05)

    def _create_tracker(self, frame: np.ndarray, bbox: tuple) -> tuple:
        """Create and initialize an OpenCV tracker for the given bbox.

        bbox is (x1,y1,x2,y2) - convert to (x,y,w,h) for tracker.
        Returns (tracker, init_bbox).
        """
        x1, y1, x2, y2 = bbox
        w = max(2, x2 - x1)
        h = max(2, y2 - y1)
        init_bb = (x1, y1, w, h)

        # Prefer MOSSE for speed, fallback to CSRT if available
        tracker = None
        try:
            if hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerMOSSE_create'):
                tracker = cv2.legacy.TrackerMOSSE_create()
            elif hasattr(cv2, 'TrackerMOSSE_create'):
                tracker = cv2.TrackerMOSSE_create()
            elif hasattr(cv2, 'TrackerCSRT_create'):
                tracker = cv2.TrackerCSRT_create()
            elif hasattr(cv2, 'legacy') and hasattr(cv2.legacy, 'TrackerCSRT_create'):
                tracker = cv2.legacy.TrackerCSRT_create()
        except Exception:
            tracker = None

        # If no tracker factory available, return None
        if tracker is None:
            return None, None

        try:
            tracker.init(frame, init_bb)
            return tracker, init_bb
        except Exception:
            return None, None

    def _iou(self, a: tuple, b: tuple) -> float:
        """Compute IoU between two boxes in (x1,y1,x2,y2) format."""
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        iw = max(0, inter_x2 - inter_x1)
        ih = max(0, inter_y2 - inter_y1)
        inter = iw * ih
        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / union

    def _sync_person_trackers(self, person_dets: List, frame: np.ndarray) -> None:
        """Match detected persons to existing trackers or create new ones."""
        now = time.time()

        unmatched_det = []
        used_tracker_ids = set()

        # Try to match each detection to an existing tracker by IoU
        for det in person_dets:
            x1, y1, x2, y2 = det.bbox
            best_id = None
            best_iou = 0.0
            for tid, info in list(self.person_trackers.items()):
                tbbox = info.get('bbox')
                if tbbox is None:
                    continue
                # convert tracker bbox (x,y,w,h) -> x1,y1,x2,y2
                tx, ty, tw, th = tbbox
                tbox = (int(tx), int(ty), int(tx + tw), int(ty + th))
                i = self._iou((x1, y1, x2, y2), tbox)
                if i > best_iou:
                    best_iou = i
                    best_id = tid

            if best_id is not None and best_iou > 0.4:
                # Update existing tracker bbox to detected bbox (re-init for stability)
                tracker = self.person_trackers[best_id]['tracker']
                tracker_bbox = (x1, y1, x2 - x1, y2 - y1)
                try:
                    tracker.clear()
                except Exception:
                    pass
                try:
                    tracker.init(frame, tracker_bbox)
                except Exception:
                    # If re-init fails, recreate tracker
                    new_tracker, init_bb = self._create_tracker(frame, det.bbox)
                    if new_tracker is not None:
                        self.person_trackers[best_id]['tracker'] = new_tracker
                        self.person_trackers[best_id]['bbox'] = init_bb
                self.person_trackers[best_id]['bbox'] = (x1, y1, x2 - x1, y2 - y1)
                self.person_trackers[best_id]['last_seen'] = now
                used_tracker_ids.add(best_id)
            else:
                unmatched_det.append(det)

        # Create trackers for unmatched detections
        for det in unmatched_det:
            new_tracker, init_bb = self._create_tracker(frame, det.bbox)
            if new_tracker is None:
                continue
            tid = self._next_tracker_id
            self._next_tracker_id += 1
            self.person_trackers[tid] = {
                'tracker': new_tracker,
                'bbox': init_bb,
                'last_seen': now,
            }

        # Prune stale trackers not updated recently
        stale = []
        for tid, info in list(self.person_trackers.items()):
            if now - info.get('last_seen', 0) > 3.0:
                stale.append(tid)
        for tid in stale:
            try:
                del self.person_trackers[tid]
            except KeyError:
                pass

    def _update_person_trackers(self, frame: np.ndarray) -> None:
        """Update tracker positions on the current frame and refresh last_seen if successful."""
        now = time.time()
        for tid, info in list(self.person_trackers.items()):
            tracker = info.get('tracker')
            if tracker is None:
                continue
            try:
                ok, bb = tracker.update(frame)
            except Exception:
                ok = False
                bb = None
            if not ok or bb is None:
                # do not remove immediately; allow a grace period
                continue
            # bb -> (x,y,w,h)
            info['bbox'] = (int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3]))
            info['last_seen'] = now

    def stop(self, timeout: float = 1.0) -> None:
        """Stop ingestion and AI threads, release resources, and clear queues."""
        self.stopped = True

        # Release capture to unblock any ongoing read()
        try:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
        except Exception:
            pass

        # Wake up queue consumer/producers
        try:
            while not self.Q.empty():
                try:
                    self.Q.get_nowait()
                except Exception:
                    break
        except Exception:
            pass

        # Join threads (don't block too long)
        try:
            if hasattr(self, 'thread') and self.thread.is_alive():
                self.thread.join(timeout)
        except Exception:
            pass

        try:
            if hasattr(self, 'ai_thread') and self.ai_thread.is_alive():
                self.ai_thread.join(timeout)
        except Exception:
            pass

        # Clear trackers and counters
        try:
            self.person_trackers.clear()
            self.alert_counters = {'fire': 0, 'ppe': 0, 'fall': 0}
        except Exception:
            pass


    async def recv(self):
        """Required aiortc method to retrieve the next WebRTC video frame."""
        while self.Q.empty() and not self.stopped:
            await asyncio.sleep(0.01)

        if self.stopped:
            return None

        try:
            frame_rgb = self.Q.get_nowait()

            # Draw alerts for all active detections
            active_alerts = []
            
            # Check for fall alerts (show immediately when detected)
            if self.latest_fall_detections and any(d.class_name.lower() == "fallen" for d in self.latest_fall_detections):
                active_alerts.append("FALL DETECTED - ASSISTANCE REQUIRED")
            
            # Check for fire alerts (only when confirmed)
            if self.confirmed_fire:
                active_alerts.append("FIRE DETECTED - EVACUATE IMMEDIATELY")
            
            # Check for PPE alerts (only when confirmed)
            if self.confirmed_ppe:
                active_alerts.append("PPE VIOLATION DETECTED - SAFETY GEAR MISSING")
            
            # Draw unified alert bar if any alerts are active
            if active_alerts:
                self._draw_unified_alert(frame_rgb, active_alerts)

            if self.latest_fall_detections:
                FALL_SERVICE_SINGLETON.draw_fall_boxes(frame_rgb, self.latest_fall_detections, False)  # Don't draw alert here

            FIRE_SERVICE_SINGLETON.annotate_frame(frame_rgb, self.latest_fire_detections, self.confirmed_fire)

            # Before drawing PPE results, refresh person bboxes from lightweight trackers
            if self.latest_ppe_statuses and self.person_trackers:
                # Build list of tracker bboxes in x1,y1,x2,y2
                tracker_boxes = []
                for tid, info in self.person_trackers.items():
                    tb = info.get('bbox')
                    if not tb:
                        continue
                    tx, ty, tw, th = tb
                    tracker_boxes.append((tid, (int(tx), int(ty), int(tx + tw), int(ty + th))))

                # Update statuses
                for status in self.latest_ppe_statuses:
                    best_tid = None
                    best_iou = 0.0
                    sx1, sy1, sx2, sy2 = status.person_bbox
                    for tid, tbox in tracker_boxes:
                        i = self._iou((sx1, sy1, sx2, sy2), tbox)
                        if i > best_iou:
                            best_iou = i
                            best_tid = tid
                    if best_tid is not None and best_iou > 0.15:
                        tb = self.person_trackers[best_tid]['bbox']
                        tx, ty, tw, th = tb
                        status.person_bbox = (int(tx), int(ty), int(tx + tw), int(ty + th))

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

    def _draw_unified_alert(self, frame: np.ndarray, alerts: List[str]) -> None:
        """Draw a unified alert bar showing multiple active alerts."""
        if not alerts:
            return

        h, w = frame.shape[:2]
        bar_h = 60  # Increased height for multiple alerts
        alert_color = (255, 0, 0)  # RGB Red
        
        # Create blinking effect
        if int(time.time() * 2) % 2 == 0:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, h - bar_h), (w, h), alert_color, -1)
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
            
            # Draw each alert on a separate line
            font_scale = 0.55
            line_height = 18
            start_y = h - bar_h + 20
            
            for i, alert_text in enumerate(alerts):
                (tw, th), _ = cv2.getTextSize(alert_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
                tx = max(10, (w - tw) // 2)
                ty = start_y + (i * line_height)
                cv2.putText(frame, alert_text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1)

        # Draw red border
        border = frame.copy()
        cv2.rectangle(border, (0, 0), (w, h), alert_color, 8)
        cv2.addWeighted(border, 0.6, frame, 0.4, 0, frame)

    def _send_alert_notification(self, alert_message: str, violation_type: str | None = None) -> None:
        """Send alert notification to ntfy.sh with image, time, and camera name.

        This uses per-violation cooldowns controlled by `self.alert_last_sent`.
        """
        if not self.endpoint:
            return

        current_time = time.time()

        # If violation_type provided, check per-type cooldown
        if violation_type is not None:
            last = self.alert_last_sent.get(violation_type, 0)
            if current_time - last < NOTIFY_COOLDOWN_SECONDS:
                return

        try:
            from datetime import datetime
            import base64

            alert_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            url = f"https://ntfy.sh/{self.endpoint}"

            # Annotate a snapshot with alert info overlay
            frame = self.current_inference_frame
            if frame is not None:
                snapshot = frame.copy()
                h, w = snapshot.shape[:2]
                # Draw semi-transparent info bar at the top
                overlay = snapshot.copy()
                cv2.rectangle(overlay, (0, 0), (w, 52), (30, 30, 30), -1)
                cv2.addWeighted(overlay, 0.75, snapshot, 0.25, 0, snapshot)
                cv2.putText(snapshot, f"{alert_message}",
                            (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 1)
                cv2.putText(snapshot, f"Camera: {self.camera_name}  |  {alert_time}",
                            (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1)

                _, buf = cv2.imencode(".jpg", snapshot, [cv2.IMWRITE_JPEG_QUALITY, 80])
                image_bytes = buf.tobytes()

                # Send image as attachment with metadata in headers
                response = requests.post(
                    url,
                    data=image_bytes,
                    headers={
                        "Title":    f"{alert_message}",
                        "Message":  f"Camera: {self.camera_name} | Time: {alert_time}",
                        "Filename": "alert.jpg",
                        "Content-Type": "image/jpeg",
                        "Tags":     "warning,camera",
                        "Priority": "high",
                    },
                    timeout=10,
                )
            else:
                # No frame available — send plain text with metadata
                body = f"{alert_message}\nCamera: {self.camera_name}\nTime: {alert_time}"
                response = requests.post(url, data=body.encode("utf-8"),
                                         headers={"Title": alert_message, "Priority": "high"},
                                         timeout=5)

            if response.status_code == 200:
                # Update per-violation last-sent timestamp if provided
                if violation_type is not None:
                    self.alert_last_sent[violation_type] = current_time
                # Keep legacy global timestamp too
                self.last_alert_time = current_time
                print(f"[ALERT] Sent to {url}: {alert_message} | {self.camera_name} | {alert_time}")
            else:
                print(f"[ALERT] Failed HTTP {response.status_code} for {url}")

        except Exception as e:
            print(f"[ALERT] Error sending notification: {e}")


class StreamManager:
    """
    Maintains a dictionary of active streams to avoid duplicating threads
    if multiple users request the exact same target URL.
    """
    def __init__(self):
        self.active_tracks = {}

    def get_or_create_track(self, camera_url: str, monitored_ppe: list = None, endpoint: str = None, camera_name: str = None) -> NetworkCameraTrack:
        if camera_url in self.active_tracks:
            track = self.active_tracks[camera_url]
            if track.stopped:
                print(f"[StreamManager] Existing track has already stopped for {camera_url}. Creating a new one.")
                self.active_tracks.pop(camera_url, None)
            else:
                print(f"[StreamManager] Reusing existing track for {camera_url}")
                if monitored_ppe is not None:
                    track.monitored_ppe = monitored_ppe
                if endpoint is not None:
                    track.endpoint = endpoint
                if camera_name is not None:
                    track.camera_name = camera_name
                return track
            
        print(f"[StreamManager] Provisioning NEW Track for {camera_url}")
        track = NetworkCameraTrack(camera_url, endpoint, camera_name)
        if monitored_ppe is not None:
            track.monitored_ppe = monitored_ppe
        self.active_tracks[camera_url] = track
        return track
    
    def get_track(self, camera_url: str) -> NetworkCameraTrack:
        """Get an existing track without creating one."""
        return self.active_tracks.get(camera_url)
        
    def close_track(self, camera_url: str):
        if camera_url in self.active_tracks:
            track = self.active_tracks.pop(camera_url)
            track.stop()

# Singleton instance exported for main.py
stream_factory = StreamManager()
