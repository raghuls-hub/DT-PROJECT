import os
from dotenv import load_dotenv

load_dotenv()  # Loads .env file

# ── MongoDB Atlas ──
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB  = "smart_safety_system"

AVAILABLE_PPE_OPTIONS = [
    "Hardhat", "Mask", "Person", "Safety Vest"
]

# The 3 items users can specifically "mark" for detection
MONITORED_PPE_TYPES = ["Hardhat", "Mask", "Safety Vest"]

PPE_NEGATIVE_MAP = {
    "Hardhat": "NO-Hardhat",
    "Mask": "NO-Mask",
    "Safety Vest": "NO-Safety Vest"
}

# The actual indices in basic-model.pt (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)
# 0: Hardhat, 1: Mask, 5: Person, 7: Safety Vest
YOLO_CLASSES = [
    "Hardhat", "Mask", "NO-Hardhat", "NO-Mask", "NO-Safety Vest", 
    "Person", "Safety Cone", "Safety Vest", "machinery", "vehicle"
]

PPE_VIOLATION_THRESHOLD = int(os.getenv("PPE_VIOLATION_THRESHOLD", "15"))

PPE_CONFIDENCE_THRESHOLD  = float(os.getenv("PPE_CONFIDENCE_THRESHOLD",  "0.45"))
PPE_IOU_THRESHOLD         = float(os.getenv("PPE_IOU_THRESHOLD",         "0.40"))

FIRE_CONFIDENCE_THRESHOLD = float(os.getenv("FIRE_CONFIDENCE_THRESHOLD", "0.40"))
FIRE_IOU_THRESHOLD        = float(os.getenv("FIRE_IOU_THRESHOLD",        "0.45"))

FALL_CONFIDENCE_THRESHOLD = float(os.getenv("FALL_CONFIDENCE_THRESHOLD", "0.50"))
