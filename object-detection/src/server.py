"""
Object Detection Server for Video Processing Pipeline
Uses YOLO12 for real-time object detection on video frames
"""

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
import cv2
import numpy as np
from ultralytics import YOLO
import io
import base64
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Load YOLO12 model (using nano version for efficiency)
# Model will be downloaded automatically on first run
print("Loading YOLO12 model...")
model = YOLO('yolo12n.pt')  # yolo12n.pt is the nano version (fastest)
print("Model loaded successfully!")

# Configuration
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.25'))
IOU_THRESHOLD = float(os.getenv('IOU_THRESHOLD', '0.45'))
MAX_DETECTIONS = int(os.getenv('MAX_DETECTIONS', '300'))

def allowed_file(filename):
    """Check if file has allowed extension"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def encode_image_to_base64(img):
    """Encode OpenCV image to base64 string"""
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model': 'YOLOv11-nano',
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/detect', methods=['POST'])
@cross_origin(origin="*")
def detect_objects():
    """
    Detect objects in uploaded image
    Expects: multipart/form-data with 'image' file
    Returns: JSON with detections and annotated image
    """
    try:
        # Check if the request contains a file
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        file = request.files['image']

        # Check if the file is valid
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, bmp, gif, tiff'}), 400

        # Read and decode image
        file_bytes = np.frombuffer(file.read(), np.uint8)
        img_data = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if img_data is None:
            return jsonify({'error': 'Failed to decode image'}), 400

        # Get original image dimensions
        height, width, channels = img_data.shape

        # Perform object detection
        results = model(
            img_data,
            conf=CONFIDENCE_THRESHOLD,
            iou=IOU_THRESHOLD,
            max_det=MAX_DETECTIONS,
            verbose=False
        )

        # Process detection results
        detections = []
        result = results[0]
        
        for box in result.boxes:
            # Extract detection information
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            confidence = float(box.conf[0].cpu().numpy())
            class_id = int(box.cls[0].cpu().numpy())
            class_name = model.names[class_id]
            
            detection = {
                'class': class_name,
                'class_id': class_id,
                'confidence': confidence,
                'bbox': {
                    'x1': float(x1),
                    'y1': float(y1),
                    'x2': float(x2),
                    'y2': float(y2)
                }
            }
            detections.append(detection)

        # Generate annotated image
        annotated_img = result.plot()  # YOLOv11 built-in visualization
        annotated_base64 = encode_image_to_base64(annotated_img)

        # Prepare response
        response = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'image_dimensions': {
                'width': width,
                'height': height
            },
            'detection_count': len(detections),
            'detections': detections,
            'annotated_image': annotated_base64,
            'model_info': {
                'model': 'YOLOv11-nano',
                'confidence_threshold': CONFIDENCE_THRESHOLD,
                'iou_threshold': IOU_THRESHOLD
            }
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/detect/batch', methods=['POST'])
@cross_origin(origin="*")
def detect_objects_batch():
    """
    Detect objects in multiple uploaded images
    Expects: multipart/form-data with multiple 'images' files
    Returns: JSON array with detections for each image
    """
    try:
        if 'images' not in request.files:
            return jsonify({'error': 'No image files provided'}), 400

        files = request.files.getlist('images')
        
        if len(files) == 0:
            return jsonify({'error': 'No files selected'}), 400

        results_list = []
        
        for idx, file in enumerate(files):
            if not allowed_file(file.filename):
                results_list.append({
                    'file_index': idx,
                    'filename': file.filename,
                    'success': False,
                    'error': 'Invalid file type'
                })
                continue

            # Read and decode image
            file_bytes = np.frombuffer(file.read(), np.uint8)
            img_data = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            
            if img_data is None:
                results_list.append({
                    'file_index': idx,
                    'filename': file.filename,
                    'success': False,
                    'error': 'Failed to decode image'
                })
                continue

            # Perform detection
            detections = []
            result = model(img_data, conf=CONFIDENCE_THRESHOLD, verbose=False)[0]
            
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                confidence = float(box.conf[0].cpu().numpy())
                class_id = int(box.cls[0].cpu().numpy())
                class_name = model.names[class_id]
                
                detections.append({
                    'class': class_name,
                    'class_id': class_id,
                    'confidence': confidence,
                    'bbox': {
                        'x1': float(x1),
                        'y1': float(y1),
                        'x2': float(x2),
                        'y2': float(y2)
                    }
                })

            results_list.append({
                'file_index': idx,
                'filename': file.filename,
                'success': True,
                'detection_count': len(detections),
                'detections': detections
            })

        return jsonify({
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'total_images': len(files),
            'results': results_list
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/info', methods=['GET'])
def model_info():
    """Get information about the model and available classes"""
    return jsonify({
        'model': 'YOLOv11-nano',
        'num_classes': len(model.names),
        'classes': model.names,
        'configuration': {
            'confidence_threshold': CONFIDENCE_THRESHOLD,
            'iou_threshold': IOU_THRESHOLD,
            'max_detections': MAX_DETECTIONS
        }
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    print(f"Starting Object Detection Server on port {port}")
    print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD}")
    print(f"IOU Threshold: {IOU_THRESHOLD}")
    app.run(host='0.0.0.0', port=port, debug=False)


