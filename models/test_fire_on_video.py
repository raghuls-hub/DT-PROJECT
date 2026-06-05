import cv2
import os
import sys
import numpy as np
import time

# Add backend to path so we can import services
sys.path.append(os.path.join(os.getcwd(), "backend"))
from models.fire_service import FireService

# 1. SETUP
MODEL_PATH = os.path.join("models", "fire_detection.onnx")
INPUT_VIDEO = os.path.join("videos", "input.mp4")
OUTPUT_VIDEO = "output_test_fire.mp4"

print(f"🔥 Initializing Fire Service with model: {MODEL_PATH}")
fire_service = FireService(MODEL_PATH)

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

print("Processing frames (this may take a while)...")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    if frame_count % 10 == 0:
        print(f"Frame {frame_count}/{total_frames if total_frames > 0 else '???'}")

    # 1. The FireService expects standard BGR frames for inference (it's consistent with YOLO internal handling)
    # Note: Inside stream_manager we convert to RGB for WebRTC, but FireService.detect_fire uses it directly.
    
    # 2. Inference (detections are scaled internally to the input frame size by YOLO)
    detections = fire_service.detect_fire(frame)
    
    # 3. Annotate (Boxes + Alerts)
    if detections:
        fire_service.annotate_frame(frame, detections)
    
    # 4. Final write to disk
    out.write(frame)

cap.release()
out.release()

print(f"\nSUCCESS! Processed {frame_count} frames.")
print(f"Output saved to: {os.path.abspath(OUTPUT_VIDEO)}")
