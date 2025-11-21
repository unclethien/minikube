# Object Detection Component

Component 3 of the Video Processing Security System - Multi-resolution real-time object detection using YOLO12

## Overview

This component provides multi-resolution object detection for video frames using YOLO12-nano. It receives frames from the cluster component in 3 resolutions (256p, 720p, 1080p), processes them in parallel, and streams annotated results to the outputstreaming service.

**Version:** 2.1.0 (Multi-Resolution + Flexible Parsing)

## Features

### Core Capabilities
- **Multi-Resolution Processing**: Parallel processing of 256p, 720p, 1080p frames
- **YOLO12-nano Detection**: Fast CPU-optimized object detection
- **Flexible Input Parsing**: Handles both standard file uploads and base64-encoded data
- **Topic-Based Routing**: Kafka topic metadata passed to outputstreaming
- **Thread-Safe Processing**: ThreadPoolExecutor with model locking
- **Streaming Endpoints**: MJPEG streaming and latest-frame APIs

### Performance
- **<500ms**: 3-resolution parallel processing
- **~24 fps**: Throughput with 2 replicas
- **<1.5GB**: Docker image size (CPU-optimized)
- **Zero Collisions**: Thread-safe filename indexing

### Integration
- **Cluster Input**: Multipart/form-data from cluster component
- **Outputstreaming Output**: Resolution-specific endpoints with topic metadata
- **PostgreSQL Storage**: Optional database persistence (disabled by default)
- **K3s Deployment**: Horizontal autoscaling, health checks, resource limits

## Architecture

```
Cluster Component (10.42.0.198, 10.42.3.52)
    ↓ POST /detect/batch (multipart/form-data)
    ├─ Files: 256.png, 720.png, 1080.png (base64 or binary)
    └─ Metadata: topic (video_frames, video_frames2)
    ↓
Object Detection Service
    ├─ parse_cluster_request() → Extract images + topic
    ├─ decode_image_file() → Handle base64/binary
    ├─ process_resolutions_parallel() → ThreadPoolExecutor
    │   ├─ 256p → YOLO inference
    │   ├─ 720p → YOLO inference
    │   └─ 1080p → YOLO inference
    └─ send_to_outputstreaming() → With topic metadata
    ↓
Outputstreaming Service (8080)
    ├─ POST /frame/256p {frame, topic, resolution}
    ├─ POST /frame/720p {frame, topic, resolution}
    └─ POST /frame/1080p {frame, topic, resolution}
```

## API Endpoints

### Detection Endpoints

#### `POST /detect/batch`
**Primary endpoint for cluster integration** - Processes 3 resolutions in parallel

**Input:** `multipart/form-data`
- Files: `256.png`, `720.png`, `1080.png` (base64-encoded or binary)
- Metadata: `topic` field (e.g., `video_frames`)

**Output:** JSON
```json
{
  "success": true,
  "correlation_id": "uuid-here",
  "source_topic": "video_frames",
  "results": [
    {"resolution": "256p", "indexed_filename": "...", "detection_count": 5},
    {"resolution": "720p", "indexed_filename": "...", "detection_count": 5},
    {"resolution": "1080p", "indexed_filename": "...", "detection_count": 5}
  ],
  "processing_time_ms": 347.2,
  "timestamp": "2025-11-21T01:30:00Z"
}
```

**Behavior:**
- Decodes all 3 images (binary or base64)
- Processes in parallel using ThreadPoolExecutor
- Sends annotated frames to outputstreaming with topic metadata
- Returns correlation ID linking all 3 resolutions

#### `POST /detect/256p`, `/detect/720p`, `/detect/1080p`
Single-resolution detection endpoints

**Input:** `multipart/form-data` with image file
**Output:** JSON with detections + sends to outputstreaming

#### `POST /detect`
Legacy single-frame detection (backward compatibility)

### Streaming Endpoints

#### `GET /stream/{resolution}/latest`
Get latest annotated frame for resolution (256p, 720p, 1080p)

**Output:** PNG image with bounding boxes
**Headers:** `X-Frame-ID`, `X-Frame-Timestamp`, `X-Detection-Count`

#### `GET /stream/{resolution}`
MJPEG streaming for resolution

**Output:** `multipart/x-mixed-replace` stream (5 FPS)
**Query Params:** `?start_time=2025-11-21T00:00:00Z` (ISO 8601)

See [STREAMING_ENDPOINTS.md](STREAMING_ENDPOINTS.md) for details.

### Health & Info

#### `GET /health`
Health check endpoint

**Output:**
```json
{
  "status": "healthy",
  "model": "YOLO12-nano",
  "timestamp": "2025-11-21T01:30:00Z"
}
```

#### `GET /info`
Service information and configuration

## Configuration

### Environment Variables

**Required:**
- `OUTPUTSTREAMING_URL_256P` - Outputstreaming endpoint for 256p frames
- `OUTPUTSTREAMING_URL_720P` - Outputstreaming endpoint for 720p frames
- `OUTPUTSTREAMING_URL_1080P` - Outputstreaming endpoint for 1080p frames

**Optional:**
- `ENABLE_DB_STORAGE` - Enable PostgreSQL storage (default: `false`)
- `SEND_TO_OUTPUTSTREAMING` - Enable outputstreaming (default: `true`)
- `CONFIDENCE_THRESHOLD` - YOLO confidence threshold (default: `0.25`)
- `IOU_THRESHOLD` - YOLO IOU threshold (default: `0.45`)
- `MAX_DETECTIONS` - Max detections per image (default: `100`)
- `MAX_IMAGE_SIZE_MB` - Max upload size per image (default: `10`)
- `IMAGE_INDEX_PREFIX` - Pod-specific prefix for filenames (default: `pod`)

**Database (if ENABLE_DB_STORAGE=true):**
- `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`

## Deployment

### K3s Deployment

```bash
# Apply manifests
kubectl apply -f k8s/

# Check status
kubectl get pods -l app=object-detection
kubectl logs -f -l app=object-detection

# Scale
kubectl scale deployment object-detection --replicas=3
```

### Docker Build

```bash
# Build for linux/amd64
docker build --platform linux/amd64 -t object-detection:latest .

# Save and transfer
docker save object-detection:latest -o object-detection.tar
scp object-detection.tar user@node:~/

# Import on K3s worker node
ssh user@worker "sudo k3s ctr images import /tmp/object-detection.tar"

# Restart deployment
kubectl rollout restart deployment object-detection
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete instructions.

## Recent Changes

### v2.1.0 - Flexible Parsing (2025-11-21)
- **Fixed:** Handles cluster sending base64 images without proper file encoding
- **Added:** Raw multipart parsing with regex extraction
- **Added:** Automatic detection of binary vs base64 content
- **Performance:** <50ms parsing overhead

### v2.0.0 - Multi-Resolution (2025-11-19)
- **Added:** Parallel processing of 3 resolutions (<500ms total)
- **Added:** Topic-based routing to outputstreaming
- **Added:** Thread-safe indexed filename generation
- **Added:** MJPEG streaming endpoints
- **Changed:** Database storage optional (disabled by default)

See [CHANGELOG.md](CHANGELOG.md) for full history.

## Testing

### Local Testing

```bash
# Run test script
python test_base64_fix.py

# Test with curl
curl -X POST http://localhost:8000/detect/batch \
  -F "256.png=@test_256.png" \
  -F "720.png=@test_720.png" \
  -F "1080.png=@test_1080.png" \
  -F "topic=video_frames"
```

### Production Monitoring

```bash
# Watch logs
kubectl logs -f -l app=object-detection | grep -E "INFO|ERROR|WARN"

# Check metrics
kubectl top pods -l app=object-detection

# Test health
curl http://object-detection-service:8000/health
```

## Troubleshooting

### 400 Errors from Cluster

**Symptoms:** `[ERROR] /detect/batch validation failed: Missing required file: 256.png`

**Causes:**
1. Cluster not sending files (check `request.files: []`)
2. Cluster configuration pointing to wrong URL
3. Network issues between cluster and object detection

**Solutions:**
1. Verify `NEXT_PROCESSING_STAGE_URL` in cluster config
2. Check cluster logs for sending errors
3. Test with curl to isolate issue

### Topic Shows as "unknown"

**Symptoms:** `topic=unknown` in logs

**Cause:** Topic metadata not sent or not parsed correctly

**Solutions:**
1. Check cluster sends topic in multipart data
2. Verify regex pattern matches format
3. Add query parameter: `/detect/batch?topic=video_frames`

### Slow Processing (>500ms)

**Causes:**
1. Large image sizes (>10MB)
2. Too many detections (>100 objects)
3. Insufficient CPU resources

**Solutions:**
1. Reduce image sizes at cluster level
2. Increase `MAX_DETECTIONS` threshold
3. Scale up replicas or CPU limits

## Performance

### Benchmarks
- **Single Frame:** ~150-200ms (1920x1080)
- **3 Resolutions Parallel:** ~350-450ms
- **Throughput (2 replicas):** ~24 frames/sec
- **Memory per Pod:** ~1.5-2GB
- **CPU per Pod:** 0.5-1.5 cores

### Resource Limits (K3s)
```yaml
resources:
  requests:
    memory: "1Gi"
    cpu: "500m"
  limits:
    memory: "3Gi"
    cpu: "2000m"
```

## Documentation

- [API_ENDPOINTS.md](API_ENDPOINTS.md) - Complete API reference
- [STREAMING_ENDPOINTS.md](STREAMING_ENDPOINTS.md) - Streaming API details
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment procedures
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [plans/](../plans/) - Implementation plans and phase documentation

## License

Internal use only - UTD CS6343 Course Project
