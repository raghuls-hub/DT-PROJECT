import cv2
import time
import threading
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

    POSITIVE_COLOR = (0, 200, 0)        # Green (RGB)
    NEGATIVE_COLOR = (255, 0, 0)        # Red (RGB)
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

        self.device = 'cpu'
        print(f"[PPEService] Loading basic model on CPU: {model_path}")

        self.model = YOLO(model_path, task='detect')

        # Warm-up pass
        print("[PPEService] Running warm-up pass...")
        dummy = np.zeros((360, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False, device=self.device)

        print("[PPEService] Model ready.")

    def detect_ppe(self, frame: np.ndarray) -> List[PPEDetection]:
        """Run inference and return all raw detections."""
        try:
            results = self.model.predict(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                verbose=False,
                device=self.device
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
        monitored_items: List[str] = MONITORED_PPE_TYPES,
    ) -> List[PersonPPEStatus]:
        """Group PPE detections by person and identify violations."""
        monitored_set = set(monitored_items)
        people: List[PPEDetection] = []
        ppe_items: List[tuple[str, float, float]] = []

        for det in detections:
            if det.class_name == "Person":
                people.append(det)
            elif det.class_name in monitored_set:
                x1, y1, x2, y2 = det.bbox
                ppe_items.append((det.class_name, (x1 + x2) * 0.5, (y1 + y2) * 0.5))

        if not people:
            return []

        person_statuses: List[PersonPPEStatus] = []
        monitored_items = [item for item in monitored_items if item in monitored_set]

        # Pre-compute PPE centers and create lookup sets for faster processing
        ppe_centers = [(class_name, cx, cy) for class_name, cx, cy in ppe_items]
        
        for p in people:
            status = PersonPPEStatus(p.bbox)
            px1, py1, px2, py2 = p.bbox
            present_ppe = set()

            # Use set for faster lookups and batch processing
            for class_name, cx, cy in ppe_centers:
                if px1 <= cx <= px2 and py1 <= cy <= py2:
                    present_ppe.add(class_name)

            status.present_ppe = sorted(present_ppe)
            status.missing_ppe = [item for item in monitored_items if item not in present_ppe]
            status.violations = bool(status.missing_ppe)
            person_statuses.append(status)

        return person_statuses

    def draw_ppe_alert(self, frame: np.ndarray, is_confirmed: bool = False) -> None:
        if not is_confirmed:
            return

        h, w = frame.shape[:2]
        bar_h = 48
        alert_text = "PPE VIOLATION DETECTED - SAFETY GEAR MISSING"
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

    def draw_ppe_results(
        self,
        frame: np.ndarray,
        person_statuses: List[PersonPPEStatus],
        raw_detections: List[PPEDetection],
        is_confirmed: bool = False
    ) -> None:
        """Draw person boxes with violation alerts and their associated PPE."""
        # Alert is now handled by unified system in stream_manager
        
        # Draw Person Boxes and Alerts
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


# ─── Attendance-specific PPE detection (isolated, separate thread) ─────────────

# Class-specific colors for attendance drawing (BGR)
_ATTENDANCE_CLASS_COLORS: Dict[str, Tuple[int, int, int]] = {
    "Hardhat":     (0, 200, 0),      # Green
    "Mask":        (255, 165, 0),    # Orange
    "Safety Vest": (0, 180, 255),    # Cyan
    "Person":      (200, 200, 200),  # Grey
}
_ATTENDANCE_DEFAULT_COLOR = (180, 180, 0)  # Yellow for any other class

_attendance_lock = threading.Lock()


def detect_ppe_for_attendance(
    service: "PPEService",
    frame: np.ndarray,
    required_ppe: List[str],
) -> dict:
    """
    Attendance-specific PPE detection.
    - Runs under a thread lock so it never interferes with live monitoring.
    - Detects ALL PPE classes directly (no person-centric logic required).
    - Draws labeled bounding boxes for every detected class on the frame.
    - Returns detected classes, missing classes, and whether all required PPE is present.
    """
    with _attendance_lock:
        try:
            results = service.model.predict(
                frame,
                conf=service.confidence_threshold,
                iou=service.iou_threshold,
                verbose=False,
                device=service.device,
            )
        except Exception as exc:
            print(f"[PPEService][Attendance] Inference error: {exc}")
            return {
                "detected_ppe": [],
                "missing_ppe": required_ppe,
                "ppe_verified": False,
                "message": f"Inference error: {exc}",
            }

    detected_classes: List[str] = []
    boxes_out: List[dict] = []

    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_name = service.model.names[int(box.cls[0])]
            conf     = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            # BGR → send as [R,G,B] so frontend can use rgba()
            bgr = _ATTENDANCE_CLASS_COLORS.get(cls_name, _ATTENDANCE_DEFAULT_COLOR)
            boxes_out.append({
                "class_name": cls_name,
                "conf": round(conf, 2),
                "bbox": [x1, y1, x2, y2],
                "color": [bgr[2], bgr[1], bgr[0]],
            })

            if cls_name in MONITORED_PPE_TYPES and cls_name not in detected_classes:
                detected_classes.append(cls_name)

    required_set = set(required_ppe)
    detected_set = set(detected_classes)
    missing      = sorted(required_set - detected_set)
    ppe_verified = len(missing) == 0 and bool(required_set)

    return {
        "detected_ppe": detected_classes,
        "missing_ppe":  missing,
        "ppe_verified": ppe_verified,
        "boxes":        boxes_out,
        "message":      "All PPE detected" if ppe_verified else f"Missing: {', '.join(missing)}",
    }
