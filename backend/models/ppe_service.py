import cv2
import numpy as np
from typing import List, Tuple, Optional, Dict
from ultralytics import YOLO

import sys
import os
# ensure we can import config properly
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import (
    PPE_CONFIDENCE_THRESHOLD,
    PPE_IOU_THRESHOLD,
    AVAILABLE_PPE_OPTIONS,
    PPE_NEGATIVE_MAP,
    MONITORED_PPE_TYPES,
)


class PPEDetection:
    """Represents a single PPE detection result."""

    def __init__(
        self,
        class_name: str,
        confidence: float,
        bbox: Tuple[int, int, int, int],
    ):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox            # (x1, y1, x2, y2)

    def __repr__(self) -> str:
        return f"PPEDetection({self.class_name}, conf={self.confidence:.2f})"


class PersonPPEStatus:
    """Status of a person with their associated PPE."""

    def __init__(self, person_bbox: Tuple[int, int, int, int]):
        self.person_bbox = person_bbox
        self.present_ppe: List[str] = []
        self.missing_ppe: List[str] = []
        self.violations: bool = False


class PPEService:
    """YOLO-based PPE detection service using ONNX optimizations.
    Implements Person-centric logic: Detect Person -> Check PPE on Person.
    """

    POSITIVE_COLOR = (0, 200, 0)        # Green  — PPE present
    NEGATIVE_COLOR = (0, 0, 255)        # Red    — PPE missing / violation
    LABEL_COLOR    = (255, 255, 255)    # White
    FONT           = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = PPE_CONFIDENCE_THRESHOLD,
        iou_threshold: float        = PPE_IOU_THRESHOLD,
    ):
        self.confidence_threshold = confidence_threshold
        self.iou_threshold        = iou_threshold

        print(f"[PPEService] Loading basic model: {model_path}")
        self.model = YOLO(model_path, task='detect')

        # Warm-up pass
        print("[PPEService] Running warm-up pass...")
        dummy = np.zeros((360, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False)
        print("[PPEService] Model ready.")

    def detect_ppe(self, frame: np.ndarray) -> List[PPEDetection]:
        """Run inference and return all raw detections."""
        try:
            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
            )
            detections: List[PPEDetection] = []
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_name = self.model.names[int(box.cls[0])]
                    # Only use allowed classes
                    if cls_name not in AVAILABLE_PPE_OPTIONS:
                        continue
                    
                    conf     = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    detections.append(PPEDetection(cls_name, conf, (x1, y1, x2, y2)))

            return detections
        except Exception as exc:
            print(f"[PPEService] Error during detection: {exc}")
            return []

    def process_person_logic(
        self, 
        detections: List[PPEDetection], 
        monitored_items: List[str] = MONITORED_PPE_TYPES
    ) -> List[PersonPPEStatus]:
        """Group PPE detections by person and identify violations."""
        people = [d for d in detections if d.class_name == "Person"]
        ppe_items = [d for d in detections if d.class_name in monitored_items]
        
        person_statuses: List[PersonPPEStatus] = []

        for p in people:
            status = PersonPPEStatus(p.bbox)
            px1, py1, px2, py2 = p.bbox

            # Find PPE associated with this person
            for ppe in ppe_items:
                # Check if PPE center is inside person box
                inner_x = (ppe.bbox[0] + ppe.bbox[2]) / 2
                inner_y = (ppe.bbox[1] + ppe.bbox[3]) / 2
                
                if px1 <= inner_x <= px2 and py1 <= inner_y <= py2:
                    if ppe.class_name not in status.present_ppe:
                        status.present_ppe.append(ppe.class_name)

            # Check for missing items
            for item in monitored_items:
                if item not in status.present_ppe:
                    status.missing_ppe.append(item)
            
            status.violations = len(status.missing_ppe) > 0
            person_statuses.append(status)

        return person_statuses

    def draw_ppe_results(
        self,
        frame: np.ndarray,
        person_statuses: List[PersonPPEStatus],
        raw_detections: List[PPEDetection]
    ) -> None:
        """Draw person boxes with violation alerts and their associated PPE."""
        # 1. Draw raw PPE detections first (so they are visible)
        for det in raw_detections:
            if det.class_name == "Person": continue # Will draw separately
            
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), self.POSITIVE_COLOR, 1)
            cv2.putText(frame, det.class_name, (x1, y1-5), self.FONT, 0.4, self.POSITIVE_COLOR, 1)

        # 2. Draw Person Boxes and Alerts
        for status in person_statuses:
            x1, y1, x2, y2 = status.person_bbox
            color = self.NEGATIVE_COLOR if status.violations else self.POSITIVE_COLOR
            thickness = 2 if status.violations else 1
            
            # Draw Person Box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            
            # Draw Alert Label
            label = "OK" if not status.violations else f"VIOLATION: Missing {', '.join(status.missing_ppe)}"
            (tw, th), _ = cv2.getTextSize(label, self.FONT, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 5, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 7), self.FONT, 0.5, self.LABEL_COLOR, 1)
