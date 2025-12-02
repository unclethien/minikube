"""
Object Detection Server for Video Processing Pipeline
Uses YOLO12 for real-time object detection on video frames
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS, cross_origin
from flask_sqlalchemy import SQLAlchemy
import cv2
import numpy as np
from ultralytics import YOLO
import requests
import base64
import os
import io
import re
import threading
import uuid
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

# Database storage configuration (disabled by default)
ENABLE_DB_STORAGE = os.getenv('ENABLE_DB_STORAGE', 'false').lower() == 'true'

# Use SQLite in-memory as dummy DB when database is disabled (no PostgreSQL connection needed)
# This satisfies flask-sqlalchemy without requiring psycopg2 or a real database
if ENABLE_DB_STORAGE:
    from urllib.parse import quote_plus
    db_user = os.environ.get('DB_USER', 'postgres')
    db_pass = os.environ.get('DB_PASSWORD', 'postgres')
    db_host = os.environ.get('DB_HOST', 'postgres-svc')
    db_port = os.environ.get('DB_PORT', '5432')
    db_name = os.environ.get('DB_NAME', 'postgres')
    DATABASE_URI = f"postgresql://{quote_plus(db_user)}:{quote_plus(db_pass)}@{db_host}:{db_port}/{db_name}"
    print("[INFO] Database storage is ENABLED - connecting to PostgreSQL")
else:
    DATABASE_URI = "sqlite:///:memory:"
    print("[INFO] Database storage is DISABLED - using in-memory SQLite (no DB operations)")

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

# Outputstreaming configuration - resolution-specific endpoints
OUTPUTSTREAMING_URL_256P = os.getenv('OUTPUTSTREAMING_URL_256P')
OUTPUTSTREAMING_URL_720P = os.getenv('OUTPUTSTREAMING_URL_720P')
OUTPUTSTREAMING_URL_1080P = os.getenv('OUTPUTSTREAMING_URL_1080P')

# Fallback to old single URL format for backward compatibility
OUTPUTSTREAMING_URL_BASE = os.getenv('OUTPUTSTREAMING_URL', 'http://outputstreaming-service:8080/frame')

# Build resolution-to-URL mapping
OUTPUTSTREAMING_URLS = {
    '256p': OUTPUTSTREAMING_URL_256P or f"{OUTPUTSTREAMING_URL_BASE}/256p",
    '720p': OUTPUTSTREAMING_URL_720P or f"{OUTPUTSTREAMING_URL_BASE}/720p",
    '1080p': OUTPUTSTREAMING_URL_1080P or f"{OUTPUTSTREAMING_URL_BASE}/1080p",
}

SEND_TO_OUTPUTSTREAMING = os.getenv('SEND_TO_OUTPUTSTREAMING', 'true').lower() == 'true'

# Log outputstreaming configuration on startup
if SEND_TO_OUTPUTSTREAMING:
    print("[INFO] Outputstreaming endpoints configured:")
    for res, url in OUTPUTSTREAMING_URLS.items():
        print(f"  {res}: {url}")

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
IMAGE_INDEX_PREFIX = os.getenv('IMAGE_INDEX_PREFIX', 'pod')

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


def send_frame_to_outputstreaming(img, resolution='unknown', source_topic='unknown'):
    """
    Send annotated frame to outputstreaming service

    Args:
        img: Annotated image (numpy array)
        resolution: Resolution label (256p, 720p, 1080p)
        source_topic: Source topic name for filtering (e.g., 'video_frames')
    """
    if not SEND_TO_OUTPUTSTREAMING:
        return

    # Get resolution-specific URL from mapping
    url = OUTPUTSTREAMING_URLS.get(resolution)
    if not url:
        print(f"[WARN] No outputstreaming URL configured for resolution: {resolution}")
        return

    try:
        # Encode image as PNG (preserves original format)
        _, img_encoded = cv2.imencode('.png', img)
        img_base64 = base64.b64encode(img_encoded.tobytes()).decode('utf-8')

        # Send as JSON to resolution-specific endpoint with topic metadata
        response = requests.post(
            url,
            json={
                'frame': img_base64,
                'topic': source_topic,
                'resolution': resolution
            },
            timeout=2
        )
        if response.status_code == 200:
            print(f"[INFO] Frame sent to outputstreaming ({resolution}, topic={source_topic}): {url}")
        else:
            print(f"[WARN] Outputstreaming returned {response.status_code} for {resolution}")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Failed to send frame to outputstreaming ({resolution}): {str(e)}")

def generate_correlation_id():
    """Generate UUID v4 correlation ID for linking multi-resolution frames"""
    return str(uuid.uuid4())

def decode_image_file(file_obj):
    """
    Decode image from binary or base64-encoded content

    Handles both:
    1. Raw binary PNG/JPEG data (standard multipart/form-data)
    2. Base64-encoded image data (cluster sends this incorrectly)

    Args:
        file_obj: Flask FileStorage object

    Returns:
        numpy.ndarray: Decoded image or None if decoding fails
    """
    try:
        content = file_obj.read()
        content_size = len(content)

        print(f"[DEBUG] Decoding {file_obj.filename}: size={content_size} bytes, first_20_bytes={content[:20]}")

        # Try decoding as raw binary first (standard format)
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is not None:
            print(f"[DEBUG] Binary decode SUCCESS: {file_obj.filename} -> shape={img.shape}")
            return img

        # Fallback: Try base64 decoding (cluster sends this)
        try:
            decoded = base64.b64decode(content)
            nparr = np.frombuffer(decoded, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is not None:
                print(f"[INFO] Base64 decode SUCCESS: {file_obj.filename} -> shape={img.shape}")
                return img
        except Exception as b64_error:
            print(f"[WARN] Base64 decode FAILED for {file_obj.filename}: {b64_error}")

        print(f"[ERROR] All decode attempts FAILED for {file_obj.filename}")
        return None

    except Exception as e:
        print(f"[ERROR] Image decode exception for {file_obj.filename}: {e}")
        return None

def parse_cluster_request(request):
    """
    Parse cluster multipart request with 3 resolution files + JSON metadata

    FLEXIBLE PARSING:
    - Method 1: Standard Flask request.files (if cluster sends files properly)
    - Method 2: Extract base64 images from raw multipart data (cluster workaround)

    Expected format:
    - Files: 256.png, 720.png, 1080.png (or any names with these patterns)
    - JSON metadata: {"topic": "video_frames"}

    Returns:
        tuple: (files_dict, metadata_dict, errors)
    """
    errors = []
    files_dict = {}

    # Expected file names from cluster
    expected_files = ['256.png', '720.png', '1080.png']

    # Method 1: Try standard Flask file parsing first
    if request.files:
        print(f"[DEBUG] Found files in request.files: {list(request.files.keys())}")
        for filename in expected_files:
            if filename in request.files:
                file_obj = request.files[filename]
                decoded_img = decode_image_file(file_obj)

                if decoded_img is None:
                    errors.append(f"Invalid or corrupt image: {filename}")
                else:
                    files_dict[filename] = decoded_img
            else:
                errors.append(f"Missing required file: {filename}")

    # Method 2: If no files found, parse from raw multipart data
    # This handles cluster sending base64 data without proper file encoding
    elif request.data:
        print(f"[DEBUG] No files in request.files, parsing raw multipart data...")
        try:
            data_str = request.data.decode('utf-8', errors='ignore')

            # Extract base64-encoded images from multipart boundaries
            for filename in expected_files:
                # Pattern: name="256.png"\r\n\r\n<base64_data>
                pattern = rf'name="{re.escape(filename)}"\r?\n\r?\n([A-Za-z0-9+/=]+)'
                match = re.search(pattern, data_str, re.MULTILINE | re.DOTALL)

                if match:
                    base64_data = match.group(1).strip()
                    # Clean up base64 (remove newlines, boundaries)
                    base64_data = re.sub(r'[\r\n-]+', '', base64_data)

                    try:
                        # Decode base64
                        img_bytes = base64.b64decode(base64_data)
                        # Decode image
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        decoded_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                        if decoded_img is not None:
                            files_dict[filename] = decoded_img
                            print(f"[INFO] Extracted {filename} from raw multipart data ({len(img_bytes)} bytes)")
                        else:
                            errors.append(f"Failed to decode extracted image: {filename}")
                    except Exception as e:
                        errors.append(f"Base64 decode error for {filename}: {str(e)}")
                else:
                    errors.append(f"Missing required file: {filename}")

        except Exception as e:
            print(f"[ERROR] Failed to parse raw multipart data: {e}")
            errors.append(f"Multipart parsing error: {str(e)}")
    else:
        errors.append("No image data received (empty request.files and request.data)")

    # Parse topic metadata from raw multipart data
    metadata = {}
    topic = 'unknown'

    if request.data:
        try:
            data_str = request.data.decode('utf-8', errors='ignore')
            # Pattern matches: name="topic"\r\n\r\nvideo_frames
            topic_match = re.search(r'name="topic"\r?\n\r?\n([^\r\n]+)', data_str)
            if topic_match:
                topic = topic_match.group(1).strip()
        except Exception as e:
            print(f"[WARN] Failed to parse topic from raw multipart data: {e}")

    # Fallback: Check query parameters
    if topic == 'unknown' and 'topic' in request.args:
        topic = request.args.get('topic')

    # Log warning if topic couldn't be extracted
    if topic == 'unknown':
        print(f"[WARN] Topic could not be extracted from request")

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

        # Send to outputstreaming with resolution and topic
        send_frame_to_outputstreaming(annotated_img, resolution, source_topic)

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
        files_dict: Dict of {filename: file_object} or {filename: numpy_array}
        correlation_id: UUID linking all resolutions
        source_topic: Kafka topic name

    Returns:
        list: Results for each resolution
    """
    import time
    start_time = time.time()

    # Read all files first (I/O outside thread pool)
    # Handle both FileStorage objects and pre-decoded numpy arrays
    files_data = {}
    for filename, file_obj_or_array in files_dict.items():
        # Check if already decoded (numpy array)
        if isinstance(file_obj_or_array, np.ndarray):
            # Already decoded by parse_cluster_request
            file_bytes = cv2.imencode('.png', file_obj_or_array)[1].tobytes()
        else:
            # FileStorage object - read as usual
            file_bytes = file_obj_or_array.read()

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

        # DEBUG LOGGING - capture exact validation failure details
        print(f"[DEBUG] /detect/batch request received from {request.remote_addr}")
        print(f"[DEBUG] Request files: {list(request.files.keys())}")
        print(f"[DEBUG] Files decoded successfully: {list(files_dict.keys())}")
        print(f"[DEBUG] Metadata extracted: {metadata}")
        print(f"[DEBUG] Parse errors: {parse_errors}")

        if parse_errors:
            error_response = {
                'success': False,
                'error': 'Invalid request format',
                'details': parse_errors,
                'expected_files': ['256.png', '720.png', '1080.png'],
                'expected_metadata': {'topic': 'string'},
                'received_files': list(request.files.keys()),
                'files_decoded': list(files_dict.keys())
            }
            print(f"[ERROR] /detect/batch validation failed: {error_response}")
            return jsonify(error_response), 400

        source_topic = metadata['topic']
        correlation_id = generate_correlation_id()

        print(f"[INFO] Processing cluster batch: topic={source_topic}, correlation_id={correlation_id}")

        # Phase 1C: Process resolutions in parallel
        results = process_resolutions_parallel(files_dict, correlation_id, source_topic)

        # Store successful results in database (if enabled)
        if ENABLE_DB_STORAGE:
            successful_results = [r for r in results if r.get('success', False)]
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

@app.route('/detect/<resolution>', methods=['POST'])
@cross_origin(origin="*")
def detect_resolution_specific(resolution):
    """
    Detect objects at specific resolution (256p, 720p, 1080p)
    Endpoints: /detect/256p, /detect/720p, /detect/1080p
    Expects: multipart/form-data with image file (any field name, already resized by upstream)
    Optional: 'topic' form field for source topic identification
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

        # Get optional topic parameter
        source_topic = request.form.get('topic', 'direct_upload')

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

        # Send to outputstreaming with resolution and topic
        send_frame_to_outputstreaming(annotated_img, resolution, source_topic)

        # Encode annotated image as PNG
        _, img_encoded = cv2.imencode('.png', annotated_img)
        img_bytes = img_encoded.tobytes()

        # Store in database (if enabled)
        if ENABLE_DB_STORAGE:
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
                print(f"[WARN] Failed to store in DB: {str(db_error)}")
                db.session.rollback()
                # Continue without failing
        else:
            print(f"[INFO] Database storage disabled - frame forwarded to outputstreaming only")

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
        }        }), 200

# Database model for storing detection results (optional - only used if ENABLE_DB_STORAGE=true)
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    print(f"Starting Object Detection Server on port {port}")
    print(f"Confidence Threshold: {CONFIDENCE_THRESHOLD}")
    print(f"IOU Threshold: {IOU_THRESHOLD}")
    app.run(host='0.0.0.0', port=port, debug=False)


