import cv2
import numpy as np
from typing import List, Tuple, Optional
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
        self.bbox = bbox            # (x1, y1, x2, y2) in the caller's coordinate space

    def __repr__(self) -> str:
        return f"PPEDetection({self.class_name}, conf={self.confidence:.2f})"


class PPEService:
    """YOLO-based PPE detection service using ONNX optimizations.

    Instantiated once sequentially and reused across threads securely thanks to decoupling.
    """

    POSITIVE_COLOR = (0, 200, 0)        # Green  — PPE present
    NEGATIVE_COLOR = (0, 80, 255)       # Orange-red — PPE missing / violation
    FONT           = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = PPE_CONFIDENCE_THRESHOLD,
        iou_threshold: float        = PPE_IOU_THRESHOLD,
    ):
        self.confidence_threshold = confidence_threshold
        self.iou_threshold        = iou_threshold

        print(f"[PPEService] Loading ONNX model natively via YOLO wrapper: {model_path}")
        # YOLO native class natively integrates ONNXRuntime-GPU under the hood if it is installed
        self.model = YOLO(model_path, task='detect')

        # Warm-up pass
        print("[PPEService] Running ONNX runtime warm-up pass...")
        dummy = np.zeros((360, 640, 3), dtype=np.uint8)
        self.model.predict(dummy, verbose=False)
        print("[PPEService] Model loaded and warmed up.")

    # ── Detection ─────────────────────────────────────────────────────────────

    def detect_ppe(self, frame: np.ndarray) -> List[PPEDetection]:
        """Run inference on a 640x360 frame."""
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
                    conf     = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    detections.append(PPEDetection(cls_name, conf, (x1, y1, x2, y2)))

            detections.sort(key=lambda d: d.confidence, reverse=True)
            return detections

        except Exception as exc:
            print(f"[PPEService] Detection error: {exc}")
            return []

    # ── Validation ────────────────────────────────────────────────────────────

    def verify_ppe(
        self,
        detected_classes: List[str],
        required_ppe: List[str],
    ) -> Tuple[bool, List[str], List[str]]:
        if not required_ppe:
            return True, [], list(detected_classes)

        missing: List[str] = []
        present: List[str] = []

        for item in required_ppe:
            pos          = item in detected_classes
            neg_cls      = PPE_NEGATIVE_MAP.get(item, "")
            neg_detected = (neg_cls in detected_classes) if neg_cls else False

            if pos and not neg_detected:
                present.append(item)
            else:
                missing.append(item)

        return len(missing) == 0, missing, present

    def get_detected_class_names(self, detections: List[PPEDetection]) -> List[str]:
        """Return the unique set of class names from a detection list."""
        return list({d.class_name for d in detections})

    # ── Drawing ───────────────────────────────────────────────────────────────

    def draw_ppe_boxes(
        self,
        frame: np.ndarray,
        detections: List[PPEDetection],
        required_ppe: Optional[List[str]] = None,
    ) -> None:
        if required_ppe:
            allowed = set()
            for item in required_ppe:
                allowed.add(item)
                neg = PPE_NEGATIVE_MAP.get(item)
                if neg:
                    allowed.add(neg)
        else:
            allowed = set(AVAILABLE_PPE_OPTIONS) | set(PPE_NEGATIVE_MAP.values())

        for det in detections:
            if det.class_name not in allowed:
                # Debug logging to catch naming mismatches
                print(f"[Draw Debug] Skipping '{det.class_name}' because it's not in allowed: {list(allowed)[:3]}...")
                continue

            x1, y1, x2, y2 = det.bbox
            # Final verification of coordinates
            print(f"[Draw Debug] Drawing '{det.class_name}' at {det.bbox} on frame {frame.shape}")
            
            label = f"{det.class_name} {det.confidence:.0%}"
            color = (
                self.NEGATIVE_COLOR
                if det.class_name.startswith("NO-")
                else self.POSITIVE_COLOR
            )

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            (tw, th), _ = cv2.getTextSize(label, self.FONT, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(
                frame, label,
                (x1 + 2, y1 - 4),
                self.FONT, 0.5, (255, 255, 255), 1,
            )
