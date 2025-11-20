"""
Object Detection Server for Video Processing Pipeline
Uses YOLO12 for real-time object detection on video frames
"""

from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS, cross_origin
from flask_sqlalchemy import SQLAlchemy
import cv2
import numpy as np
from ultralytics import YOLO
import requests
import base64
import os
import io
import threading
import socket
import uuid
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

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
OUTPUTSTREAMING_URL = os.getenv('OUTPUTSTREAMING_URL', 'http://outputstreaming-service:8080/frame')
SEND_TO_OUTPUTSTREAMING = os.getenv('SEND_TO_OUTPUTSTREAMING', 'true').lower() == 'true'

# Multi-resolution configuration
RESOLUTIONS = {
    '256p': (256, 256),
    '720p': (1280, 720),
    '1080p': (1920, 1080)
}

# Image counter for indexed filenames (thread-safe)
image_counter = 0
counter_lock = threading.Lock()

# YOLO model lock for thread-safe inference (Phase 1C)
model_lock = threading.Lock()

# Pod-specific prefix for distributed deployments
IMAGE_INDEX_PREFIX = os.getenv('IMAGE_INDEX_PREFIX', socket.gethostname())
OUTPUT_DIR = os.getenv('OUTPUT_DIR', '/data/image')

# Security configuration
MAX_IMAGE_SIZE_MB = int(os.getenv('MAX_IMAGE_SIZE_MB', '10'))  # 10MB default
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

def get_next_image_index():
    """
    Thread-safe increment and return next image index

    Returns:
        int: Next sequential index for filename generation
    """
    global image_counter
    with counter_lock:
        image_counter += 1
        return image_counter

def generate_indexed_filename(resolution, index=None, ext='.png'):
    """
    Generate indexed filename with timestamp and resolution

    Format: YYYYMMDD_HHMMSS_<pod-prefix>_<index>_<resolution>.png
    Example: 20251119_161345_pod-abc_000123_720p.png

    Args:
        resolution (str): Resolution label (256p, 720p, 1080p)
        index (int, optional): Image index. If None, get next automatically
        ext (str): File extension (default: .png)

    Returns:
        str: Generated filename
    """
    import re

    if index is None:
        index = get_next_image_index()

    # Counter rollover at 999,999 for 6-digit format
    if index > 999999:
        print(f"[WARN] Counter exceeded 999,999, rolling over to 1")
        global image_counter
        with counter_lock:
            image_counter = 1
        index = 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Stronger pod prefix sanitization (alphanumeric, dash, underscore only)
    prefix = re.sub(r'[^a-zA-Z0-9_-]', '-', IMAGE_INDEX_PREFIX)[:20]

    filename = f"{timestamp}_{prefix}_{index:06d}_{resolution}{ext}"
    return filename

def validate_image_size(file_bytes):
    """
    Validate uploaded image size to prevent DoS attacks

    Args:
        file_bytes (bytes): Image file bytes

    Raises:
        ValueError: If image exceeds size limit
    """
    size_mb = len(file_bytes) / (1024 * 1024)

    if len(file_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError(
            f'Image too large: {size_mb:.2f}MB exceeds limit of {MAX_IMAGE_SIZE_MB}MB'
        )


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

def generate_correlation_id():
    """Generate UUID v4 correlation ID for linking multi-resolution frames"""
    return str(uuid.uuid4())

def parse_cluster_request(request):
    """
    Parse cluster multipart request with 3 resolution files + JSON metadata

    Expected format:
    - Files: 256.png, 720.png, 1080.png
    - JSON body or form field: {"topic": "video_frames"}

    Returns:
        tuple: (files_dict, metadata_dict, errors)
    """
    errors = []
    files_dict = {}

    # Expected file names from cluster
    expected_files = ['256.png', '720.png', '1080.png']

    # Check for each expected file
    for filename in expected_files:
        if filename in request.files:
            files_dict[filename] = request.files[filename]
        else:
            errors.append(f"Missing required file: {filename}")

    # Parse JSON metadata - try multiple sources
    metadata = {}
    try:
        # Try request.get_json() first (Content-Type: application/json)
        json_data = request.get_json(silent=True)
        if json_data:
            metadata = json_data
        # Fallback: try form data
        elif 'topic' in request.form:
            metadata = {'topic': request.form.get('topic')}
        # Fallback: try request data
        elif request.data:
            import json
            try:
                metadata = json.loads(request.data)
            except:
                pass
    except:
        pass

    # Extract topic with default
    topic = metadata.get('topic', 'unknown')

    return files_dict, {'topic': topic}, errors

def map_filename_to_resolution(filename):
    """
    Map cluster filename to resolution label

    Args:
        filename: e.g., '256.png', '720.png', '1080.png'

    Returns:
        str: Resolution label (256p, 720p, 1080p) or None
    """
    mapping = {
        '256.png': '256p',
        '720.png': '720p',
        '1080.png': '1080p'
    }
    return mapping.get(filename)

def process_single_resolution(filename, file_bytes, resolution, correlation_id, source_topic):
    """
    Process single resolution frame (Phase 1C - parallel worker)

    Args:
        filename: Original filename
        file_bytes: Image file bytes
        resolution: Resolution label (256p, 720p, 1080p)
        correlation_id: UUID linking multi-resolution frames
        source_topic: Kafka topic name

    Returns:
        dict: Processing result with success/error status
    """
    try:
        # Validate size
        validate_image_size(file_bytes)

        # Decode image
        np_arr = np.frombuffer(file_bytes, np.uint8)
        img_data = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_data is None:
            return {
                'filename': filename,
                'resolution': resolution,
                'success': False,
                'error': 'Failed to decode image'
            }

        height, width = img_data.shape[:2]

        # Generate indexed filename
        indexed_filename = generate_indexed_filename(resolution)

        # Perform object detection (thread-safe with model lock)
        with model_lock:
            detection_results = model(
                img_data,
                conf=CONFIDENCE_THRESHOLD,
                iou=IOU_THRESHOLD,
                max_det=MAX_DETECTIONS,
                verbose=False
            )

        # Process detections
        detections = []
        result = detection_results[0]

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

        # Generate annotated image
        annotated_img = result.plot()

        # Send to outputstreaming
        send_frame_to_outputstreaming(annotated_img)

        # Encode for storage
        _, img_encoded = cv2.imencode('.png', annotated_img)
        img_bytes = img_encoded.tobytes()

        # Return result for storage
        return {
            'filename': filename,
            'resolution': resolution,
            'indexed_filename': indexed_filename,
            'detection_count': len(detections),
            'detections': detections,
            'annotated_image': img_bytes,
            'image_width': width,
            'image_height': height,
            'success': True
        }

    except ValueError as e:
        # Size validation error
        return {
            'filename': filename,
            'resolution': resolution,
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        return {
            'filename': filename,
            'resolution': resolution,
            'success': False,
            'error': str(e)
        }

def process_resolutions_parallel(files_dict, correlation_id, source_topic):
    """
    Process multiple resolutions in parallel using ThreadPoolExecutor (Phase 1C)

    Args:
        files_dict: Dict of {filename: file_object}
        correlation_id: UUID linking all resolutions
        source_topic: Kafka topic name

    Returns:
        list: Results for each resolution
    """
    import time
    start_time = time.time()

    # Read all files first (I/O outside thread pool)
    files_data = {}
    for filename, file_obj in files_dict.items():
        file_bytes = file_obj.read()
        if len(file_bytes) == 0:
            # Skip empty files
            continue
        files_data[filename] = file_bytes

    results = []

    # Process resolutions in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        for filename, file_bytes in files_data.items():
            resolution = map_filename_to_resolution(filename)
            if not resolution:
                results.append({
                    'filename': filename,
                    'success': False,
                    'error': f'Unknown resolution mapping for {filename}'
                })
                continue

            # Submit processing task
            future = executor.submit(
                process_single_resolution,
                filename, file_bytes, resolution, correlation_id, source_topic
            )
            futures[future] = resolution

        # Collect results as they complete
        for future in as_completed(futures):
            resolution = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append({
                    'resolution': resolution,
                    'success': False,
                    'error': f'Thread execution error: {str(e)}'
                })

    elapsed = time.time() - start_time
    print(f"[PERF] Parallel processing: {elapsed*1000:.0f}ms for {len(results)} resolutions")

    return results


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
    Expects: multipart/form-data with image file (any field name)
    Returns: JSON with detections
    """
    try:
        # Get the first file from request (accepts any field name)
        if not request.files:
            return jsonify({'error': 'No image file provided'}), 400

        # Get first uploaded file regardless of field name
        file = next(iter(request.files.values()))

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
    Process multi-resolution frames from cluster component (Phase 1B+1C)

    Expected request format (from cluster kevin-version branch):
    - Content-Type: multipart/form-data
    - Files: 256.png, 720.png, 1080.png (any field names accepted)
    - JSON metadata: {"topic": "video_frames"} (optional)

    Returns:
        JSON with correlation_id, results for each resolution, and timestamps

    Example response:
    {
      "success": true,
      "correlation_id": "uuid-here",
      "source_topic": "video_frames",
      "results": [
        {"resolution": "256p", "indexed_filename": "...", "detection_count": 5},
        {"resolution": "720p", "indexed_filename": "...", "detection_count": 5},
        {"resolution": "1080p", "indexed_filename": "...", "detection_count": 5}
      ],
      "timestamp": "2025-11-19T17:30:00Z"
    }
    """
    import time
    start_time = time.time()

    try:
        # Parse cluster request (accept any file names)
        files_dict, metadata, parse_errors = parse_cluster_request(request)

        if parse_errors:
            return jsonify({
                'success': False,
                'error': 'Invalid request format',
                'details': parse_errors,
                'expected_files': ['256.png', '720.png', '1080.png'],
                'expected_metadata': {'topic': 'string'}
            }), 400

        source_topic = metadata['topic']
        correlation_id = generate_correlation_id()

        print(f"[INFO] Processing cluster batch: topic={source_topic}, correlation_id={correlation_id}")

        # Phase 1C: Process resolutions in parallel
        results = process_resolutions_parallel(files_dict, correlation_id, source_topic)

        # Store successful results in database
        successful_results = [r for r in results if r.get('success', False)]

        if successful_results:
            # Store each successful detection individually
            for result in successful_results:
                try:
                    detection_record = DetectionResult(
                        filename=result['filename'],
                        indexed_filename=result['indexed_filename'],
                        resolution=result['resolution'],
                        detection_count=result['detection_count'],
                        detections=result['detections'],
                        annotated_image=result['annotated_image'],
                        image_width=result['image_width'],
                        image_height=result['image_height']
                    )
                    db.session.add(detection_record)
                    db.session.commit()
                    print(f"[INFO] Stored detection result in DB (filename: {result['indexed_filename']})")
                except Exception as db_error:
                    print(f"[ERROR] Failed to store in DB: {str(db_error)}")
                    db.session.rollback()
                    # Mark this result as failed
                    result['success'] = False
                    result['error'] = 'Database insert failed'

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        # Check for failures
        successful_results = [r for r in results if r.get('success', False)]
        failed_results = [r for r in results if not r.get('success', False)]

        # Remove binary data from results for JSON serialization
        for result in results:
            result.pop('annotated_image', None)  # Remove bytes data

        # Prepare response
        response = {
            'success': len(failed_results) == 0,
            'correlation_id': correlation_id,
            'source_topic': source_topic,
            'total_resolutions': len(results),
            'successful_count': len(successful_results),
            'failed_count': len(failed_results),
            'results': results,
            'processing_time_ms': round(processing_time_ms, 2),
            'timestamp': datetime.now().isoformat()
        }

        # Return appropriate status code
        if len(failed_results) > 0:
            # Partial or complete failure
            if len(successful_results) > 0:
                # Partial failure
                print(f"[WARN] Partial failure: {len(successful_results)}/{len(results)} succeeded")
                return jsonify(response), 207  # Multi-Status
            else:
                # Complete failure
                print(f"[ERROR] Complete failure: all {len(results)} resolutions failed")
                return jsonify(response), 500
        else:
            # Complete success
            print(f"[INFO] Cluster batch complete: {processing_time_ms:.0f}ms for {len(results)} resolutions")
            return jsonify(response), 200

    except Exception as e:
        processing_time_ms = (time.time() - start_time) * 1000
        print(f"[ERROR] Cluster batch endpoint error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'processing_time_ms': round(processing_time_ms, 2),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/detect/annotated', methods=['POST'])
@cross_origin(origin="*")
def detect_objects_annotated():
    """
    Detect objects and return annotated image
    Also stores result in database with indexed filename
    Expects: multipart/form-data with image file (any field name)
    Optional: 'resolution' form field (256p, 720p, 1080p) for metadata
    Returns: Annotated image as PNG
    """
    try:
        # Get the first file from request (accepts any field name)
        if not request.files:
            return jsonify({'error': 'No image file provided'}), 400

        # Get first uploaded file regardless of field name
        file = next(iter(request.files.values()))
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Get optional resolution parameter
        resolution = request.form.get('resolution', 'unknown')

        # Read file bytes
        file_bytes = file.read()

        # Validate image size
        try:
            validate_image_size(file_bytes)
        except ValueError as e:
            return jsonify({'error': str(e)}), 413  # Payload Too Large

        # Decode image
        np_arr = np.frombuffer(file_bytes, np.uint8)
        img_data = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_data is None:
            return jsonify({'error': 'Failed to decode image'}), 400

        height, width = img_data.shape[:2]

        # Generate indexed filename
        indexed_filename = generate_indexed_filename(resolution if resolution in RESOLUTIONS else 'unknown')

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

        # Generate annotated image
        annotated_img = result.plot()

        # Send to outputstreaming
        send_frame_to_outputstreaming(annotated_img)

        # Encode annotated image as PNG
        _, img_encoded = cv2.imencode('.png', annotated_img)
        img_bytes = img_encoded.tobytes()

        # Store in database
        try:
            detection_record = DetectionResult(
                filename=file.filename,
                indexed_filename=indexed_filename,
                resolution=resolution if resolution in RESOLUTIONS else None,
                detection_count=len(detections),
                detections=detections,
                annotated_image=img_bytes,
                image_width=width,
                image_height=height
            )
            db.session.add(detection_record)
            db.session.commit()
            print(f"[INFO] Stored detection result in DB (ID: {detection_record.id}, filename: {indexed_filename})")
        except Exception as db_error:
            print(f"[ERROR] Failed to store in DB: {str(db_error)}")
            db.session.rollback()
            # Fail-fast: return error to client instead of silent failure
            return jsonify({
                'success': False,
                'error': f'Database error: {str(db_error)}',
                'timestamp': datetime.now().isoformat()
            }), 500

        # Return annotated image with indexed filename
        return send_file(
            io.BytesIO(img_bytes),
            mimetype='image/png',
            as_attachment=False,
            download_name=indexed_filename
        )

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/detect/<resolution>', methods=['POST'])
@cross_origin(origin="*")
def detect_resolution_specific(resolution):
    """
    Detect objects at specific resolution (256p, 720p, 1080p)
    Endpoints: /detect/256p, /detect/720p, /detect/1080p
    Expects: multipart/form-data with image file (any field name, already resized by upstream)
    Returns: Annotated image as PNG with indexed filename
    """
    try:
        # Validate resolution
        if resolution not in RESOLUTIONS:
            return jsonify({
                'error': f'Invalid resolution: {resolution}',
                'valid_resolutions': list(RESOLUTIONS.keys())
            }), 400

        # Get the first file from request (accepts any field name)
        if not request.files:
            return jsonify({'error': 'No image file provided'}), 400

        # Get first uploaded file regardless of field name
        file = next(iter(request.files.values()))
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Read file bytes
        file_bytes = file.read()

        # Validate image size
        try:
            validate_image_size(file_bytes)
        except ValueError as e:
            return jsonify({'error': str(e)}), 413  # Payload Too Large

        # Decode image (already at target resolution from upstream)
        np_arr = np.frombuffer(file_bytes, np.uint8)
        img_data = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_data is None:
            return jsonify({'error': 'Failed to decode image'}), 400

        height, width = img_data.shape[:2]

        # Generate indexed filename
        indexed_filename = generate_indexed_filename(resolution)

        # Perform object detection on image as-is (no resizing)
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

        # Generate annotated image
        annotated_img = result.plot()

        # Send to outputstreaming
        send_frame_to_outputstreaming(annotated_img)

        # Encode annotated image as PNG
        _, img_encoded = cv2.imencode('.png', annotated_img)
        img_bytes = img_encoded.tobytes()

        # Store in database
        try:
            detection_record = DetectionResult(
                filename=file.filename,
                indexed_filename=indexed_filename,
                resolution=resolution,
                detection_count=len(detections),
                detections=detections,
                annotated_image=img_bytes,
                image_width=width,
                image_height=height
            )
            db.session.add(detection_record)
            db.session.commit()
            print(f"[INFO] Stored detection result in DB (ID: {detection_record.id}, filename: {indexed_filename})")
        except Exception as db_error:
            print(f"[ERROR] Failed to store in DB: {str(db_error)}")
            db.session.rollback()
            # Fail-fast: return error to client instead of silent failure
            return jsonify({
                'success': False,
                'error': f'Database error: {str(db_error)}',
                'timestamp': datetime.now().isoformat()
            }), 500

        # Return annotated image with indexed filename
        return send_file(
            io.BytesIO(img_bytes),
            mimetype='image/png',
            as_attachment=False,
            download_name=indexed_filename
        )

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
        'resolutions': list(RESOLUTIONS.keys()),
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

# Database model for storing detection results
class DetectionResult(db.Model):
    __tablename__ = 'detection_results'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))  # Original uploaded filename
    indexed_filename = db.Column(db.String(300))  # Generated indexed filename
    resolution = db.Column(db.String(10))  # Resolution label (256p, 720p, 1080p)
    detection_count = db.Column(db.Integer)
    detections = db.Column(db.JSON)  # Store detection data as JSON
    annotated_image = db.Column(db.LargeBinary)  # Store annotated image as binary
    image_width = db.Column(db.Integer)
    image_height = db.Column(db.Integer)
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

@app.route('/detections', methods=['GET'])
def get_detections():
    """
    Get list of all detection records (without images)

    Query params:
    - limit: Number of results (default: 50)
    - offset: Pagination offset (default: 0)
    - resolution: Filter by resolution (optional)
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        resolution = request.args.get('resolution', None, type=str)

        # Build query with optional filters
        query = DetectionResult.query

        if resolution:
            query = query.filter_by(resolution=resolution)

        results = query.order_by(
            DetectionResult.created_at.desc()
        ).limit(limit).offset(offset).all()

        records = []
        for result in results:
            records.append({
                'id': result.id,
                'filename': result.filename,
                'indexed_filename': result.indexed_filename,
                'resolution': result.resolution,
                'detection_count': result.detection_count,
                'detections': result.detections,
                'image_width': result.image_width,
                'image_height': result.image_height,
                'created_at': result.created_at.isoformat() if result.created_at else None
            })

        return jsonify({
            'success': True,
            'count': len(records),
            'resolution_filter': resolution,
            'records': records
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/detections/<int:detection_id>/image', methods=['GET'])
def get_detection_image(detection_id):
    """Get annotated image for a specific detection"""
    try:
        result = DetectionResult.query.get(detection_id)
        if not result:
            return jsonify({'error': 'Detection not found'}), 404

        if not result.annotated_image:
            return jsonify({'error': 'No image stored'}), 404

        return send_file(
            io.BytesIO(result.annotated_image),
            mimetype='image/png',
            as_attachment=False,
            download_name=f'detection_{detection_id}_{result.filename}'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Streaming Endpoints (Phase 1 & 2)

@app.route('/stream/<resolution>/latest', methods=['GET'])
@cross_origin(origin="*")
def get_latest_frame(resolution):
    """
    Get most recent annotated frame for resolution (Phase 1)

    Returns PNG image with custom headers
    """
    try:
        # Validate resolution
        if resolution not in RESOLUTIONS:
            return jsonify({
                'error': f'Invalid resolution: {resolution}',
                'valid_resolutions': list(RESOLUTIONS.keys())
            }), 400

        # Query latest frame
        result = DetectionResult.query.filter_by(
            resolution=resolution
        ).order_by(
            DetectionResult.created_at.desc()
        ).first()

        # Handle no frames found
        if not result or not result.annotated_image:
            return jsonify({
                'error': f'No frames found for resolution {resolution}'
            }), 404

        # Prepare response
        response = send_file(
            io.BytesIO(result.annotated_image),
            mimetype='image/png',
            as_attachment=False
        )

        # Add custom headers
        response.headers['X-Frame-ID'] = str(result.id)
        response.headers['X-Frame-Timestamp'] = result.created_at.isoformat()
        response.headers['X-Detection-Count'] = str(result.detection_count)
        response.headers['Cache-Control'] = 'max-age=1, must-revalidate'

        return response

    except Exception as e:
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

def format_mjpeg_frame(image_bytes):
    """
    Format PNG binary as MJPEG frame with multipart boundary (Phase 2)

    Args:
        image_bytes: PNG binary data (BYTEA from DB)

    Returns:
        bytes: Formatted multipart frame
    """
    return (
        b'--frame\r\n'
        b'Content-Type: image/png\r\n'
        b'Content-Length: ' + str(len(image_bytes)).encode() + b'\r\n\r\n'
        + image_bytes + b'\r\n'
    )

def get_frames_since(resolution, last_timestamp, limit=10):
    """
    Get frames newer than timestamp (Phase 2)

    Args:
        resolution: Resolution label (256p, 720p, 1080p)
        last_timestamp: datetime or None
        limit: Max frames to fetch

    Returns:
        list: DetectionResult objects
    """
    query = DetectionResult.query.filter_by(resolution=resolution)

    if last_timestamp:
        query = query.filter(DetectionResult.created_at > last_timestamp)

    return query.order_by(
        DetectionResult.created_at.asc()
    ).limit(limit).all()

def generate_mjpeg_stream(resolution, start_time=None):
    """
    Generate MJPEG stream for resolution (Phase 2)

    Args:
        resolution: Resolution label (256p, 720p, 1080p)
        start_time: Optional datetime for historical playback

    Yields:
        bytes: MJPEG frame data
    """
    # Initialize cursor
    if start_time:
        last_timestamp = start_time
    else:
        # Start from most recent frame
        latest = DetectionResult.query.filter_by(
            resolution=resolution
        ).order_by(
            DetectionResult.created_at.desc()
        ).first()

        if latest:
            last_timestamp = latest.created_at - timedelta(seconds=1)
        else:
            last_timestamp = datetime.now()

    # Stream timeout (5 minutes)
    timeout = time.time() + 300
    frame_delay = 0.2  # 5 FPS

    while time.time() < timeout:
        # Query frames since last timestamp
        frames = get_frames_since(resolution, last_timestamp, limit=10)

        if frames:
            # Stream available frames
            for frame in frames:
                yield format_mjpeg_frame(frame.annotated_image)
                last_timestamp = frame.created_at
                time.sleep(frame_delay)
        else:
            # No new frames, wait and retry
            time.sleep(frame_delay)

@app.route('/stream/<resolution>', methods=['GET'])
@cross_origin(origin="*")
def stream_resolution(resolution):
    """
    MJPEG streaming endpoint for resolution (Phase 2)

    Query params:
        start_time: Optional ISO timestamp for historical playback
                   (e.g., 2025-11-19T10:00:00)

    Returns:
        Streaming response with multipart/x-mixed-replace
    """
    try:
        # Validate resolution
        if resolution not in RESOLUTIONS:
            return jsonify({
                'error': f'Invalid resolution: {resolution}',
                'valid_resolutions': list(RESOLUTIONS.keys())
            }), 400

        # Parse start_time parameter
        start_time = None
        start_time_str = request.args.get('start_time')

        if start_time_str:
            try:
                # Parse ISO format: 2025-11-19T10:00:00
                start_time = datetime.fromisoformat(start_time_str)
            except ValueError:
                return jsonify({
                    'error': 'Invalid start_time format. Use ISO format: 2025-11-19T10:00:00'
                }), 400

        # Return streaming response
        return Response(
            generate_mjpeg_stream(resolution, start_time),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Connection': 'keep-alive',
                'X-Stream-FPS': '5',
                'X-Stream-Resolution': resolution
            }
        )

    except Exception as e:
        return jsonify({
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    print(f"Starting Object Detection Server on port {port}")
    print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD}")
    print(f"IOU Threshold: {IOU_THRESHOLD}")
    app.run(host='0.0.0.0', port=port, debug=False)


