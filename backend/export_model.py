from ultralytics import YOLO
import sys

def main():
    # Convert Fire
    import os
    ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    fire_model_path = os.path.join(ROOT_DIR, "models", "fire_detection.pt")
    print(f"Loading PyTorch Fire Model: {fire_model_path}")
    fire_model = YOLO(fire_model_path)
    print("Initiating Fire ONNX export processing...")
    exported_fire = fire_model.export(format="onnx", imgsz=640, dynamic=False, simplify=True)
    print(f"Successfully exported Fire ONNX model to: {exported_fire}")

if __name__ == "__main__":
    main()
