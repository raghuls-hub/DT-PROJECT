import cv2
import os
import sys
import numpy as np

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
from models.ppe_service import PPEService
from config import MONITORED_PPE_TYPES

# 1. SETUP
MODEL_PATH = r"d:\Antigravity\DT-Project\models\basic-model.onnx"
INPUT_VIDEO = r"C:\Users\M RAGHUL\Videos\Screen Recordings\Screen Recording 2026-03-17 092333.mp4"
OUTPUT_VIDEO = "output_test_ppe_basic.mp4"

print(f"👷 Initializing PPEService (Basic) with model: {MODEL_PATH}")
ppe_service = PPEService(MODEL_PATH)

# Open Input
cap = cv2.VideoCapture(INPUT_VIDEO)
if not cap.isOpened():
    print(f"Error: Could not open input video: {INPUT_VIDEO}")
    sys.exit(1)

# Get Video Properties
width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps    = cap.get(cv2.CAP_PROP_FPS)
if fps <= 0: fps = 30.0

print(f"Input Video: {width}x{height} at {fps} FPS")
print(f"Monitoring Items: {MONITORED_PPE_TYPES}")

# Open Output
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(OUTPUT_VIDEO, fourcc, fps, (width, height))

frame_count = 0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print("Processing frames...")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    if frame_count % 10 == 0:
        print(f"Frame {frame_count}/{total_frames if total_frames > 0 else '???'}")

    # 1. Raw Detection
    raw_detections = ppe_service.detect_ppe(frame)
    
    # 2. Person-Centric Logic
    person_statuses = ppe_service.process_person_logic(raw_detections)
    
    # 3. Draw
    ppe_service.draw_ppe_results(frame, person_statuses, raw_detections)
    
    # 4. Write
    out.write(frame)

cap.release()
out.release()

print(f"\nSUCCESS! Processed {frame_count} frames.")
print(f"Output saved to: {os.path.abspath(OUTPUT_VIDEO)}")
