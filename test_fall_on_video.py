import cv2
import os
import sys
import numpy as np

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))
from models.fall_service import FallService

# 1. SETUP
MODEL_PATH = r"d:\Antigravity\DT-Project\models\fall_detection.onnx"
INPUT_VIDEO = r"d:\Antigravity\DT - PPE\videos\input.mp4"
OUTPUT_VIDEO = "output_test_fall.mp4"

print(f"🦴 Initializing Fall Service with model: {MODEL_PATH}")
fall_service = FallService(MODEL_PATH)

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

    # 2. Detect — Pass full-res frame; YOLO handles its own letterbox resize internally
    detections = fall_service.detect_fall(frame)
    
    # 3. Draw detections (coordinates are already in original frame space since YOLO handles scaling)
    if detections:
        fall_service.draw_fall_boxes(frame, detections)
    
    # 4. Write
    out.write(frame)

cap.release()
out.release()

print(f"\nSUCCESS! Processed {frame_count} frames.")
print(f"Output saved to: {os.path.abspath(OUTPUT_VIDEO)}")
