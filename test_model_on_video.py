import cv2
import os
import sys
import numpy as np
from pathlib import Path

# Add backend to path so we can import services
sys.path.append(os.path.join(os.getcwd(), "backend"))
from models.ppe_service import PPEService

# 1. SETUP
MODEL_PATH = r"d:\Antigravity\DT-Project\models\ppe-raghul-full.onnx"
INPUT_VIDEO = r"d:\Antigravity\DT - PPE\videos\fall.mp4"
OUTPUT_VIDEO = "output_test_ppe.mp4"

print(f"Initializing PPE Service with model: {MODEL_PATH}")
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

# Open Output
fourcc = cv2.VideoWriter_fourcc(*'mp4v') # Codec for .mp4
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

    # 1. Convert to RGB for the service (as it expects RGB from the WebRTC flow)
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # 2. Resize for inference (matching the 640x640 logic in stream_manager)
    target_size = 640
    resized_frame = cv2.resize(frame_rgb, (target_size, target_size))
    
    scale_x = width / target_size
    scale_y = height / target_size
    
    # 3. Detect
    detections = ppe_service.detect_ppe(resized_frame)
    
    # 4. Scale and Draw
    if detections:
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            det.bbox = (int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y))
        
        # Draw on the RGB frame
        ppe_service.draw_ppe_boxes(frame_rgb, detections)
    
    # 5. Convert back to BGR for VideoWriter
    output_frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    
    # Final write to disk
    out.write(output_frame)

cap.release()
out.release()

print(f"\nSUCCESS! Processed {frame_count} frames.")
print(f"Output saved to: {os.path.abspath(OUTPUT_VIDEO)}")
