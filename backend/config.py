import os

AVAILABLE_PPE_OPTIONS = [
    "helmet", "person", "safety_vest", "machinery", "mask", 
    "gloves", "goggles", "coverall", "face_shield", "earmuff"
]

PPE_NEGATIVE_MAP = {}

YOLO_CLASSES = [
    "helmet", "person", "safety_vest", "machinery", "mask", 
    "gloves", "goggles", "coverall", "face_shield", "earmuff"
]

PPE_VIOLATION_THRESHOLD = int(os.getenv("PPE_VIOLATION_THRESHOLD", "15"))

PPE_CONFIDENCE_THRESHOLD  = float(os.getenv("PPE_CONFIDENCE_THRESHOLD",  "0.45"))
PPE_IOU_THRESHOLD         = float(os.getenv("PPE_IOU_THRESHOLD",         "0.45"))

FIRE_CONFIDENCE_THRESHOLD = float(os.getenv("FIRE_CONFIDENCE_THRESHOLD", "0.40"))
FIRE_IOU_THRESHOLD        = float(os.getenv("FIRE_IOU_THRESHOLD",        "0.45"))

FALL_CONFIDENCE_THRESHOLD = float(os.getenv("FALL_CONFIDENCE_THRESHOLD", "0.65"))
