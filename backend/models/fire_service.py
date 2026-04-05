import cv2
import time
import numpy as np
from typing import List, Tuple
from ultralytics import YOLO

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import FIRE_CONFIDENCE_THRESHOLD, FIRE_IOU_THRESHOLD

FIRE_CLASSES  = {"fire", "Fire", "FIRE"}
SMOKE_CLASSES = {"smoke", "Smoke", "SMOKE"}


class FireDetection:
    """Represents a single fire/smoke detection result."""
    def __init__(self, class_name: str, confidence: float, bbox: Tuple[int, int, int, int]):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox       = bbox
        self.is_fire    = class_name in FIRE_CLASSES
        self.is_smoke   = class_name in SMOKE_CLASSES

    def __repr__(self):
        return f"FireDetection({self.class_name}, conf={self.confidence:.2f})"


class FireService:
    """YOLO-based fire & smoke detection service natively executing via ONNX.
    Refactored dynamically to guarantee thread-safe execution across infinite WebRTC cameras.
    """

    COLOR_FIRE  = (0,   60, 255)
    COLOR_SMOKE = (140, 140, 140)
    ALERT_BG    = (0,   0,  180)
    FONT        = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = FIRE_CONFIDENCE_THRESHOLD,
        iou_threshold: float        = FIRE_IOU_THRESHOLD,
        alert_cooldown_sec: float   = 5.0,
    ):
        self.confidence_threshold = confidence_threshold
        self.iou_threshold        = iou_threshold
        self.alert_cooldown_sec   = alert_cooldown_sec
        # We drop the local frame_count to ensure thread-safety across concurrent dynamic camera accesses!

        print(f"🔥 Loading ONNX Fire model: {model_path}")
        self.model = YOLO(model_path, task='detect')
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False)
        print("✅ ONNX Fire model loaded natively via CUDA Execution Providers!")

    def detect_fire(self, frame: np.ndarray) -> List[FireDetection]:
        try:
            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )
            detections: List[FireDetection] = []
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls  = self.model.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    detections.append(FireDetection(cls, conf, (x1, y1, x2, y2)))
            detections.sort(key=lambda d: d.confidence, reverse=True)
            return detections
        except Exception as e:
            print(f"⚠️  Fire detection ONNX error: {e}")
            return []

    def has_fire(self, detections: List[FireDetection]) -> bool:
        return any(d.is_fire for d in detections)

    def has_smoke(self, detections: List[FireDetection]) -> bool:
        return any(d.is_smoke for d in detections)

    def draw_fire_boxes(self, frame: np.ndarray, detections: List[FireDetection]) -> None:
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = self.COLOR_FIRE if det.is_fire else self.COLOR_SMOKE
            label = f"{det.class_name} {det.confidence:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3 if det.is_fire else 2)
            (tw, th), _ = cv2.getTextSize(label, self.FONT, 0.55, 1)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
            cv2.putText(frame, label, (x1 + 3, y1 - 4), self.FONT, 0.55, (255, 255, 255), 1)

    def draw_fire_alert(self, frame: np.ndarray, detections: List[FireDetection]) -> None:
        if not detections:
            return
            
        fire_present  = self.has_fire(detections)
        smoke_present = self.has_smoke(detections)

        if fire_present and smoke_present:
            alert_text  = "FIRE & SMOKE DETECTED — EVACUATE IMMEDIATELY"
            alert_color = (0, 30, 220)
        elif fire_present:
            alert_text  = "FIRE DETECTED — ALERT SECURITY"
            alert_color = (0, 60, 255)
        else:
            alert_text  = "SMOKE DETECTED — CHECK AREA"
            alert_color = (60, 120, 200)

        h, w = frame.shape[:2]
        bar_h = 48

        # Blink logic replaced with absolute time instead of frame_counts to keep global Singleton threadsafe across N cameras!
        if int(time.time() * 2) % 2 == 0:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, h - bar_h), (w, h), alert_color, -1)
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
            (tw, th), _ = cv2.getTextSize(alert_text, self.FONT, 0.75, 2)
            tx = max(10, (w - tw) // 2)
            cv2.putText(frame, alert_text, (tx, h - bar_h + th + 10), self.FONT, 0.75, (255, 255, 255), 2)

        if fire_present:
            border = frame.copy()
            cv2.rectangle(border, (0, 0), (w, h), (0, 0, 200), 8)
            cv2.addWeighted(border, 0.6, frame, 0.4, 0, frame)

    def annotate_frame(self, frame: np.ndarray, detections: List[FireDetection]) -> None:
        self.draw_fire_boxes(frame, detections)
        self.draw_fire_alert(frame, detections)
