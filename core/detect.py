import cv2
import numpy as np
from ultralytics import YOLO
import os
from django.conf import settings
from .models import Violation

# Load Haar Cascades
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')

# Load model once at startup
# Ensure you have a model file 'yolov8n.pt' or custom 'best.pt' in ml/ directory or specify path
# For this project, we download/use 'yolov8n.pt' automatically if not present
try:
    model_path = os.path.join(settings.BASE_DIR.parent, 'ml', 'yolov8n.pt') 
    model = YOLO(model_path) # It will auto-download if not found
except Exception as e:
    print(f"Error loading YOLO model: {e}")
    model = None

# Classes to detect (Standard COCO indices for YOLOv8n)
# 67: cell phone, 73: book (depends on dataset, COCO has cell phone at 67, book at 73)
# 0: person
TARGET_CLASSES = [0, 67, 73] 

def detect_violations_logic(image_data, user, exam):
    if model is None:
        return {'status': 'error', 'message': 'Model not loaded'}

    # Decode image from base64 or bytes (views.py will pass numpy array or similar)
    # Actually views.py receives base64, so it should decode it there or here. 
    # Let's assume views.py passes an OpenCV image (numpy array).
    
    img = image_data
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Haar Cascade Face & Eye Detection
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(30, 30))
    
    head_movement = False
    face_not_visible = False
    
    if len(faces) == 0:
        face_not_visible = True
    else:
        (x, y, w, h) = faces[0]
        roi_gray = gray[y:y+h, x:x+w]
        eyes = eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))
        if len(eyes) == 0:
            head_movement = True
            
    results = model(img, verbose=False)
    
    detected_violations = []
    person_count = 0
    
    for r in results:
        boxes = r.boxes
        for box in boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            
            if conf > 0.5:
                if cls == 0: # Person
                    person_count += 1
                elif cls == 67: # Mobile phone
                    detected_violations.append('Mobile Phone')
                elif cls == 73: # Book
                    detected_violations.append('Book')
    
    # Logic for violations
    final_violation = None
    
    if person_count == 0 or face_not_visible:
        final_violation = 'Face Not Visible'
        detected_violations.append('Face Not Visible')
    elif person_count > 1:
        final_violation = 'Multiple Persons'
        detected_violations.append('Multiple Persons')
    elif head_movement:
        final_violation = 'Looking Away'
        detected_violations.append('Looking Away')
    
    if 'Mobile Phone' in detected_violations:
        final_violation = 'Mobile Phone Detected'
    elif 'Book' in detected_violations:
        final_violation = 'Book Detected'
        
    if final_violation:
        # Save violation to DB (Throttle this in production to avoid spamming DB)
        # For this logic, we return the violation and let views.py decide to save or throttle
        return {
            'status': 'violation',
            'violation_type': final_violation,
            'details': detected_violations
        }
        
    return {'status': 'clean'}
