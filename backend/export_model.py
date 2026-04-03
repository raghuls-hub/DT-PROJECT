from ultralytics import YOLO

def main():
    model_path = r"d:\Antigravity\DT-Project\models\PPE_detection.pt"
    print(f"Loading PyTorch Model: {model_path}")
    model = YOLO(model_path)
    
    print("Initiating ONNX export processing...")
    # Exporting for fixed size (imgsz=640) for max speed natively
    exported_path = model.export(format="onnx", imgsz=640, dynamic=False, simplify=True)
    
    print(f"Successfully exported ONNX model to: {exported_path}")

if __name__ == "__main__":
    main()
