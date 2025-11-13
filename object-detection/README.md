# Object Detection Component

Component 3 of the Video Processing Security System - Real-time object detection using YOLO12

## Overview

This component provides real-time object detection capabilities for video frames using the YOLO12 deep learning model. It receives images from the video processing pipeline, detects objects of interest (people, vehicles, etc.), and returns detection results with bounding boxes and confidence scores. Results are stored in PostgreSQL and optionally streamed to outputstreaming service for real-time viewing.

## Features

- **YOLO12 Object Detection**: Latest YOLO model for real-time object detection
- **REST API**: Simple HTTP endpoints for easy integration
- **Batch Processing**: Support for processing multiple images
- **Annotated Output**: Returns images with bounding boxes drawn
- **PostgreSQL Storage**: Persistent storage of detection results and annotated images
- **Outputstreaming Integration**: Real-time frame streaming to outputstreaming service
- **Health Monitoring**: Built-in health check endpoints
- **Horizontal Auto-scaling**: Automatically scales based on CPU/memory usage
- **CPU-Optimized**: Efficient CPU-based inference using YOLO12-nano (~1.3GB Docker image)

## API Endpoints

### Detection Endpoints

#### `POST /detect`
Basic object detection - Returns JSON only
- **Input**: `multipart/form-data` with `image` file
- **Output**: JSON with detections, bounding boxes, and metadata

#### `POST /detect/batch`
Batch object detection - Process multiple images, sends to outputstreaming
- **Input**: `multipart/form-data` with multiple `images` files
- **Output**: JSON array with detections for each image
- **Note**: Automatically sends annotated frames to outputstreaming service

#### `POST /detect/annotated` ⭐ NEW
Detect with annotated image - Returns PNG + stores in DB + sends to outputstreaming
- **Input**: `multipart/form-data` with `image` file
- **Output**: PNG image with bounding boxes drawn
- **Features**: Returns annotated image, stores in database, streams to outputstreaming

### Database Endpoints

#### `GET /detections`
List all detection records (without images)
- **Query params**: `limit` (default: 50), `offset` (default: 0)
- **Output**: JSON array of detection metadata

#### `GET /detections/<id>/image`
Retrieve stored annotated image
- **Output**: PNG image from database

### System Endpoints

#### `GET /health`
Health check endpoint
- **Output**: Server status and model information

#### `GET /info`
Model information
- **Output**: Model details, classes, and configuration

#### `GET /test-db`
Database connection test
- **Output**: Connection status

**Complete API documentation:** See [API_ENDPOINTS.md](API_ENDPOINTS.md)

## Local Development

### Prerequisites
- Python 3.11+
- Docker Desktop
- Minikube (for Kubernetes deployment)

### Running Locally

1. Install dependencies:
```bash
cd object-detection
pip install -r requirements.txt
```

2. Run the server:
```bash
python src/server.py
```

The server will start on `http://localhost:8000`

3. Test the server:
```bash
python test_client.py http://localhost:8000 path/to/test/image.jpg
```

## Docker Deployment

### Build the Docker image:
```bash
docker build -t object-detection:latest .
```

### Run the container:
```bash
docker run -p 8000:8000 object-detection:latest
```

### Test the containerized service:
```bash
python test_client.py http://localhost:8000 test_image.jpg
```

## K3s Cluster Deployment

### Cluster Setup
This component is deployed to a K3s cluster with the following nodes:
- **Node 102** (csa-6343-102.utdallas.edu) - Control Plane
- **Node 103** (csa-6343-103.utdallas.edu) - Worker Node
- **Node 104** (csa-6343-104.utdallas.edu) - Worker Node (target for object-detection)
- **Username**: dxn210021

### Prerequisites
- Docker installed on your Mac
- Access to cluster nodes (SSH with password)
- PostgreSQL deployed in cluster (postgres-svc)
- Outputstreaming service deployed (outputstreaming-svc)

### Quick Deployment

**Complete step-by-step guide:** See [DEPLOYMENT.md](DEPLOYMENT.md)

#### Summary Steps:

1. **Build Docker image** (On Your Mac):
```bash
cd /Users/thiennguyen/Documents/GitHub/minikube/object-detection
docker build --platform linux/amd64 -t object-detection:latest .
docker save object-detection:latest -o object-detection.tar
```

2. **Transfer to Worker Node 104**:
```bash
scp object-detection.tar dxn210021@csa-6343-104.utdallas.edu:/tmp/
```

3. **Import image** (On Node 104):
```bash
ssh dxn210021@csa-6343-104.utdallas.edu
sudo /usr/local/bin/ctr -n k8s.io images import /tmp/object-detection.tar
sudo /usr/local/bin/ctr -n k8s.io images ls | grep object-detection
exit
```

4. **Transfer K8s configs** (From Your Mac):
```bash
scp k8s/deployment.yaml dxn210021@csa-6343-102.utdallas.edu:/tmp/k8s/
scp k8s/service.yaml dxn210021@csa-6343-102.utdallas.edu:/tmp/k8s/
```

5. **Label node and deploy** (On Node 102):
```bash
ssh dxn210021@csa-6343-102.utdallas.edu

# Label node 104
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml label nodes csa-6343-104.utdallas.edu workload=object-detection

# Deploy
cd /tmp/k8s/
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml apply -f deployment.yaml
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml apply -f service.yaml
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml rollout status deployment/object-detection
```

6. **Run database migration** (On Node 102):
```bash
kubectl exec -it deployment/postgres -- psql -U postgres -d postgres
# Run SQL from db/migrations/001_create_detection_results.sql
```

### Access the Service

**Internal Cluster Access**:
```bash
curl http://object-detection-svc:8000/health
```

**From Pod**:
```bash
kubectl exec -it deployment/object-detection -- curl localhost:8000/health
```

### Monitor the Deployment
```bash
# Check pods (should be on node 104)
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml get pods -l app=object-detection -o wide

# View logs
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml logs -l app=object-detection --tail=50 -f

# Check service
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml get svc object-detection-svc

# Check resource usage
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml top pods -l app=object-detection
```

## Local Testing with Minikube (Optional)

For local development and testing before VM deployment:

### 1. Start Minikube
```bash
minikube start --cpus=4 --memory=8192
```

### 2. Build image in Minikube's Docker environment
```bash
eval $(minikube docker-env)
docker build -t object-detection:latest .
```

### 3. Deploy to Minikube
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
minikube addons enable metrics-server
kubectl apply -f k8s/hpa.yaml
```

### 4. Test locally
```bash
minikube service object-detection-service --url
python test_client.py $(minikube service object-detection-service --url) test_image.jpg
```

## Configuration

### Environment Variables

**Detection Settings:**
- `PORT`: Server port (default: 8000)
- `CONFIDENCE_THRESHOLD`: Minimum confidence for detections (default: 0.25)
- `IOU_THRESHOLD`: IOU threshold for NMS (default: 0.45)
- `MAX_DETECTIONS`: Maximum detections per image (default: 300)

**Outputstreaming Integration:**
- `OUTPUTSTREAMING_URL`: Outputstreaming service URL (default: http://outputstreaming-svc:8080/frame)
- `SEND_TO_OUTPUTSTREAMING`: Enable/disable streaming (default: true)

**Database Configuration:**
- `DB_HOST`: PostgreSQL host (default: postgres-svc)
- `DB_PORT`: PostgreSQL port (default: 5432)
- `DB_NAME`: Database name (from ConfigMap: postgres-configmap)
- `DB_USER`: Database user (from Secret: postgres-secret)
- `DB_PASSWORD`: Database password (from Secret: postgres-secret)

## Resource Requirements

### CPU Deployment
- **Requests**: 500m CPU, 1Gi RAM
- **Limits**: 2000m CPU, 3Gi RAM

## Scaling

The Horizontal Pod Autoscaler (HPA) automatically scales the deployment:
- **Min replicas**: 2
- **Max replicas**: 6
- **Scale up trigger**: CPU > 70% or Memory > 80%
- **Scale down trigger**: CPU < 70% and Memory < 80%

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌──────────────────┐
│   Client/   │         │    Object        │         │  Outputstreaming │
│   Pipeline  │──POST──>│   Detection      │──Base64─>│    Service       │
│             │         │   Service        │         │  (Real-time)     │
└─────────────┘         └──────────────────┘         └──────────────────┘
                               │
                               │ YOLO12-nano
                               ▼
                        ┌──────────────┐
                        │  PostgreSQL  │
                        │  (Storage)   │
                        │ - Detections │
                        │ - Images     │
                        └──────────────┘

Integration Flow:
1. Real-time Streaming:    Image → /detect/batch → Outputstreaming → WebSocket
2. Annotated with Storage: Image → /detect/annotated → [DB + Outputstreaming + Return PNG]
3. Historical Retrieval:   /detections → List → /detections/{id}/image → Get PNG
```

## Troubleshooting

**Complete troubleshooting guide:** See [DEPLOYMENT.md](DEPLOYMENT.md#troubleshooting)

### Pods Not Starting
```bash
# Check pod events
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml describe pod <pod-name>

# Check logs
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml logs <pod-name> --tail=100

# Common issues:
# - Image not found: Re-import on node 104
# - ConfigMap/Secret missing: Check postgres-configmap and postgres-secret
# - Node label missing: Add workload=object-detection label to node 104
```

### Image Pull Errors
```bash
# Verify image on node 104
ssh dxn210021@csa-6343-104.utdallas.edu
sudo /usr/local/bin/ctr -n k8s.io images ls | grep object-detection

# If missing, re-import
sudo /usr/local/bin/ctr -n k8s.io images import /tmp/object-detection.tar
```

### Database Connection Errors
```bash
# Check postgres service
kubectl get svc postgres-svc

# Check postgres pods
kubectl get pods -l app=postgres

# Test connection from pod
kubectl exec -it deployment/object-detection -- curl localhost:8000/test-db
```

### Outputstreaming Not Receiving Frames
```bash
# Check outputstreaming service
kubectl get svc outputstreaming-svc
kubectl get pods -l app=outputstreaming

# Check logs for outputstreaming errors
kubectl logs -l app=object-detection | grep outputstreaming

# Verify environment variable
kubectl exec -it deployment/object-detection -- env | grep OUTPUTSTREAMING
```

### Kubectl Connection Refused
```bash
# Error: dial tcp [::1]:8080: connect: connection refused
# Fix: Use sudo kubectl with kubeconfig flag
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml get nodes
```

## Performance Notes

- YOLO12-nano is optimized for speed while maintaining good accuracy
- Average inference time: 50-100ms per image (CPU)
- Supports COCO dataset classes (80 classes including person, car, etc.)
- Horizontal scaling allows aggregate throughput of 20-90 images/sec
- Docker image size: ~1.3GB (optimized with CPU-only PyTorch)
- Database storage: Images stored as BYTEA, detections as JSONB

## Database Schema

See [db/migrations/001_create_detection_results.sql](db/migrations/001_create_detection_results.sql)

```sql
CREATE TABLE detection_results (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    detection_count INTEGER,
    detections JSONB,
    annotated_image BYTEA,
    image_width INTEGER,
    image_height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Future Enhancements

- [x] ~~Add PostgreSQL storage for detection results~~ ✅ Implemented
- [x] ~~Implement real-time streaming to outputstreaming service~~ ✅ Implemented
- [x] ~~Add annotated image endpoint~~ ✅ Implemented
- [ ] Add Redis caching for repeated detections
- [ ] Add support for custom trained models
- [ ] Implement detection filtering by class
- [ ] Add tracking across frames
- [ ] Implement batch retrieval of historical detections

## Documentation

- **Deployment Guide**: [DEPLOYMENT.md](DEPLOYMENT.md) - Complete step-by-step deployment instructions
- **API Reference**: [API_ENDPOINTS.md](API_ENDPOINTS.md) - Complete API documentation with examples
- **Database Migration**: [db/migrations/001_create_detection_results.sql](db/migrations/001_create_detection_results.sql)


