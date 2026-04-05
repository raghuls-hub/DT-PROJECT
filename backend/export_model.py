from ultralytics import YOLO
import sys

def main():
    # Convert Fire
    fire_model_path = r"d:\Antigravity\DT-Project\models\fire_detection.pt"
    print(f"Loading PyTorch Fire Model: {fire_model_path}")
    fire_model = YOLO(fire_model_path)
    print("Initiating Fire ONNX export processing...")
    exported_fire = fire_model.export(format="onnx", imgsz=640, dynamic=False, simplify=True)
    print(f"Successfully exported Fire ONNX model to: {exported_fire}")

if __name__ == "__main__":
    main()
