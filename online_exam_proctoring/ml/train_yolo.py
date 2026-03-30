from ultralytics import YOLO

def train_custom_yolo():
    # Load a model
    model = YOLO('yolov8n.pt')  # load a pretrained model (recommended for training)

    # Train the model
    # Ensure data.yaml is correctly configured with paths to your dataset
    results = model.train(data='data.yaml', epochs=50, imgsz=640, device='cpu')

    print("Training complete.")
    print(f"Best model saved at: {results.save_dir}")

if __name__ == '__main__':
    train_custom_yolo()
