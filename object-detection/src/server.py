"""
Object Detection Server for Video Processing Pipeline
Uses YOLO12 for real-time object detection on video frames
"""

from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from flask_sqlalchemy import SQLAlchemy
import cv2
import numpy as np
from ultralytics import YOLO
import requests
import base64
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Database configuration
db_user = os.environ.get('DB_USER', 'postgres')
db_pass = os.environ.get('DB_PASSWORD', 'postgres')
db_host = os.environ.get('DB_HOST', 'postgres-svc')
db_port = os.environ.get('DB_PORT', '5432')
db_name = os.environ.get('DB_NAME', 'postgres')

DATABASE_URI = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# Load YOLO12 model (using nano version for efficiency)
# Model will be downloaded automatically on first run
print("Loading YOLO12 model...")
model = YOLO('yolo12n.pt')  # yolo12n.pt is the nano version (fastest)
print("Model loaded successfully!")

# Configuration
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.25'))
IOU_THRESHOLD = float(os.getenv('IOU_THRESHOLD', '0.45'))
MAX_DETECTIONS = int(os.getenv('MAX_DETECTIONS', '300'))
OUTPUTSTREAMING_URL = os.getenv('OUTPUTSTREAMING_URL', 'http://outputstreaming-svc:8080/frame')
SEND_TO_OUTPUTSTREAMING = os.getenv('SEND_TO_OUTPUTSTREAMING', 'true').lower() == 'true'

def send_frame_to_outputstreaming(img):
    """Send annotated frame to outputstreaming service"""
    if not SEND_TO_OUTPUTSTREAMING:
        return

    try:
        # Encode image as PNG (preserves original format)
        _, img_encoded = cv2.imencode('.png', img)
        img_base64 = base64.b64encode(img_encoded.tobytes()).decode('utf-8')

        # Send as JSON to outputstreaming
        response = requests.post(
            OUTPUTSTREAMING_URL,
            json={'frame': img_base64},
            timeout=2
        )
        if response.status_code == 200:
            print(f"[INFO] Frame sent to outputstreaming")
        else:
            print(f"[WARN] Outputstreaming returned {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to send frame to outputstreaming: {str(e)}")

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'model': 'YOLO12-nano',
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/detect', methods=['POST'])
@cross_origin(origin="*")
def detect_objects():
    """
    Detect objects in uploaded image
    Expects: multipart/form-data with 'image' file
    Returns: JSON with detections
    """
    try:
        # Check if the request contains a file
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        file = request.files['image']

        # Check if the file is valid
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Read and decode image (OpenCV handles format validation)
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
            'model_info': {
                'model': 'YOLO12-nano',
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
            # Read and decode image with better error handling (OpenCV handles format validation)
            try:
                file_bytes = file.read()
                print(f"[DEBUG] Batch file {idx}: {file.filename}, size: {len(file_bytes)} bytes")

                if len(file_bytes) == 0:
                    results_list.append({
                        'file_index': idx,
                        'filename': file.filename,
                        'success': False,
                        'error': 'Empty file'
                    })
                    continue

                np_arr = np.frombuffer(file_bytes, np.uint8)
                img_data = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if img_data is None:
                    print(f"[ERROR] Failed to decode {file.filename}, first 20 bytes: {file_bytes[:20]}")
                    results_list.append({
                        'file_index': idx,
                        'filename': file.filename,
                        'success': False,
                        'error': 'Failed to decode image - invalid format or corrupted data'
                    })
                    continue
            except Exception as e:
                print(f"[ERROR] Exception decoding {file.filename}: {str(e)}")
                results_list.append({
                    'file_index': idx,
                    'filename': file.filename,
                    'success': False,
                    'error': f'Decode exception: {str(e)}'
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

            # Generate annotated image and send to outputstreaming
            annotated_img = result.plot()  # YOLO built-in visualization
            send_frame_to_outputstreaming(annotated_img)

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
        'model': 'YOLO12-nano',
        'num_classes': len(model.names),
        'classes': model.names,
        'configuration': {
            'confidence_threshold': CONFIDENCE_THRESHOLD,
            'iou_threshold': IOU_THRESHOLD,
            'max_detections': MAX_DETECTIONS
        }
    }), 200

# Database model for testing
class TestTable(db.Model):
    __tablename__ = 'test_object_detection'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

@app.route('/test-db', methods=['GET'])
def test_db():
    """Test database connection endpoint"""
    try:
        # Perform a simple query to test the connection
        result = db.session.query(TestTable).first()
        if result:
            return jsonify({
                'success': True,
                'data': {
                    'id': result.id,
                    'message': result.message,
                    'created_at': result.created_at.isoformat() if result.created_at else None
                }
            }), 200
        else:
            return jsonify({'success': False, 'error': 'No data found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    print(f"Starting Object Detection Server on port {port}")
    print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD}")
    print(f"IOU Threshold: {IOU_THRESHOLD}")
    app.run(host='0.0.0.0', port=port, debug=False)


