import cv2
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
        print(f"🦴 Loading ONNX Fall model: {model_path}")
        self.model = YOLO(model_path, task='detect')
        
        # Warmup
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False)
        print("✅ ONNX Fall model loaded and warmed up!")

    def detect_fall(self, frame: np.ndarray) -> List[FallDetection]:
        try:
            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                verbose=False,
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

    def draw_fall_boxes(self, frame: np.ndarray, detections: List[FallDetection]) -> None:
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = self.COLORS.get(det.class_name, (255, 255, 255))
            label = f"{det.class_name.upper()} {det.confidence:.0%}"
            
            # Draw Box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            
            # Draw Label Background
            (tw, th), _ = cv2.getTextSize(label, self.FONT, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
            
            # Draw Label Text
            cv2.putText(frame, label, (x1 + 3, y1 - 4), self.FONT, 0.6, (0, 0, 0) if det.class_name == "sitting" else (255, 255, 255), 2)
