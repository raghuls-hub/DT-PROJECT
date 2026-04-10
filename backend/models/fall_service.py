import cv2
import time
import numpy as np
from typing import List, Tuple
from ultralytics import YOLO

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import FALL_CONFIDENCE_THRESHOLD

class FallDetection:
    """Represents a single fall detection result."""
    def __init__(self, class_name: str, confidence: float, bbox: Tuple[int, int, int, int]):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox       = bbox

    def __repr__(self):
        return f"FallDetection({self.class_name}, conf={self.confidence:.2f})"

class FallService:
    """YOLO-based Fall detection service (ONNX)."""
    
    # Colors for different states
    COLORS = {
        "fallen":   (0, 0, 255),    # Red
        "sitting":  (0, 255, 255),  # Yellow
        "standing": (0, 255, 0)     # Green
    }
    FONT = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = FALL_CONFIDENCE_THRESHOLD
    ):
        self.confidence_threshold = confidence_threshold
        self.device = 'cpu'
        print(f"🦴 Loading ONNX Fall model on CPU: {model_path}")

        self.model = YOLO(model_path, task='detect')
        
        # Warmup
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False, device=self.device)
        print(f"✅ ONNX Fall model loaded and warmed up on CPU!")


    def detect_fall(self, frame: np.ndarray) -> List[FallDetection]:
        try:
            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                verbose=False,
                device=self.device
            )

            detections: List[FallDetection] = []
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls  = self.model.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    detections.append(FallDetection(cls, conf, (x1, y1, x2, y2)))
            return detections
        except Exception as e:
            print(f"⚠️ Fall detection ONNX error: {e}")
            return []

    def draw_fall_alert(self, frame: np.ndarray, is_confirmed: bool = False) -> None:
        if not is_confirmed:
            return

        h, w = frame.shape[:2]
        bar_h = 48
        alert_text = "FALL DETECTED - ASSISTANCE REQUIRED"
        alert_color = (255, 0, 0) # RGB Red

        # 1. Alert Bar (Bottom)
        if int(time.time() * 2) % 2 == 0:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, h - bar_h), (w, h), alert_color, -1)
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
            
            (tw, th), _ = cv2.getTextSize(alert_text, self.FONT, 0.65, 2)
            tx = max(10, (w - tw) // 2)
            cv2.putText(frame, alert_text, (tx, h - bar_h + th + 10), self.FONT, 0.65, (255, 255, 255), 2)

        # 2. Red Border
        border = frame.copy()
        cv2.rectangle(border, (0, 0), (w, h), alert_color, 8)
        cv2.addWeighted(border, 0.6, frame, 0.4, 0, frame)

    def draw_fall_boxes(self, frame: np.ndarray, detections: List[FallDetection], is_confirmed: bool = False) -> None:
        # Draw boxes only for fallen class to improve performance
        # Alert is now handled by unified system in stream_manager
        
        for det in detections:
            # Only draw bounding boxes for the "fallen" class
            if det.class_name.lower() != "fallen":
                continue
                
            x1, y1, x2, y2 = det.bbox
            color = (255, 0, 0)  # Red for fallen detections
            label = f"FALLEN {det.confidence:.0%}"
            
            # Draw Box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)  # Thicker box for fallen
            
            # Draw Label Background
            (tw, th), _ = cv2.getTextSize(label, self.FONT, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
            
            # Draw Label Text
            cv2.putText(frame, label, (x1 + 3, y1 - 4), self.FONT, 0.6, (255, 255, 255), 2)
