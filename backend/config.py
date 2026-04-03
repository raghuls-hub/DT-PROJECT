import os

AVAILABLE_PPE_OPTIONS = ["Hardhat", "Mask", "Safety Vest"]

PPE_NEGATIVE_MAP = {
    "Hardhat":     "NO-Hardhat",
    "Mask":        "NO-Mask",
    "Safety Vest": "NO-Safety Vest",
}

YOLO_CLASSES = [
    "Hardhat", "Mask", "NO-Hardhat", "NO-Mask",
    "NO-Safety Vest", "Person", "Safety Cone",
    "Safety Vest", "machinery", "vehicle",
]

PPE_VIOLATION_THRESHOLD = int(os.getenv("PPE_VIOLATION_THRESHOLD", "15"))

PPE_CONFIDENCE_THRESHOLD  = float(os.getenv("PPE_CONFIDENCE_THRESHOLD",  "0.45"))
PPE_IOU_THRESHOLD         = float(os.getenv("PPE_IOU_THRESHOLD",         "0.45"))
