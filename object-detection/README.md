# Object Detection Component

Component 3 of the Video Processing Security System - Real-time object detection using YOLOv11

## Overview

This component provides real-time object detection capabilities for video frames using the YOLOv11 deep learning model. It receives images from the video processing pipeline, detects objects of interest (people, vehicles, etc.), and returns detection results with bounding boxes and confidence scores.

## Features

- **YOLOv11 Object Detection**: State-of-the-art real-time object detection
- **REST API**: Simple HTTP endpoints for easy integration
- **Batch Processing**: Support for processing multiple images
- **Annotated Output**: Returns images with bounding boxes drawn
- **Health Monitoring**: Built-in health check endpoints
- **GPU Support**: Optional GPU acceleration for faster processing
- **Horizontal Auto-scaling**: Automatically scales based on CPU/memory usage

## API Endpoints

### `POST /detect`
Detect objects in a single image
- **Input**: `multipart/form-data` with `image` file
- **Output**: JSON with detections and annotated image (base64)

### `POST /detect/batch`
Detect objects in multiple images
- **Input**: `multipart/form-data` with multiple `images` files
- **Output**: JSON array with detections for each image

### `GET /health`
Health check endpoint
- **Output**: Server status and model information

### `GET /info`
Model information
- **Output**: Model details and configuration

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

## Kubernetes Deployment with Minikube

### 1. Start Minikube
```bash
minikube start --cpus=4 --memory=8192
```

### 2. Build image in Minikube's Docker environment
```bash
eval $(minikube docker-env)
docker build -t object-detection:latest .
```

### 3. Deploy to Kubernetes
```bash
# Deploy the application
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Enable metrics server (required for HPA)
minikube addons enable metrics-server

# Deploy Horizontal Pod Autoscaler
kubectl apply -f k8s/hpa.yaml
```

### 4. Access the service
```bash
# Get the service URL
minikube service object-detection-service --url

# Test the service
python test_client.py $(minikube service object-detection-service --url) test_image.jpg
```

### 5. Monitor the deployment
```bash
# Check pods
kubectl get pods -l app=object-detection

# Check HPA status
kubectl get hpa

# View logs
kubectl logs -l app=object-detection --tail=50

# Check resource usage
kubectl top pods
```

## GPU Deployment (Optional)

If you have access to a node with GPU:

```bash
kubectl apply -f k8s/gpu-deployment.yaml
```

This deployment:
- Requests a GPU resource
- Has node affinity to select GPU-enabled nodes
- Tolerates GPU node taints

## Configuration

Environment variables:
- `PORT`: Server port (default: 8000)
- `CONFIDENCE_THRESHOLD`: Minimum confidence for detections (default: 0.25)
- `IOU_THRESHOLD`: IOU threshold for NMS (default: 0.45)
- `MAX_DETECTIONS`: Maximum detections per image (default: 300)

## Resource Requirements

### CPU-based Deployment
- **Requests**: 500m CPU, 1Gi RAM
- **Limits**: 2000m CPU, 3Gi RAM

### GPU-based Deployment
- **Requests**: 1000m CPU, 2Gi RAM, 1 GPU
- **Limits**: 4000m CPU, 8Gi RAM, 1 GPU

## Scaling

The Horizontal Pod Autoscaler (HPA) automatically scales the deployment:
- **Min replicas**: 2
- **Max replicas**: 6
- **Scale up trigger**: CPU > 70% or Memory > 80%
- **Scale down trigger**: CPU < 70% and Memory < 80%

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│   Client/   │         │    Object        │         │   Storage   │
│   Rescaling │──POST──>│   Detection      │──JSON──>│   Server    │
│   Component │         │   Service        │         │             │
└─────────────┘         └──────────────────┘         └─────────────┘
                               │
                               │ YOLOv11
                               ▼
                        ┌──────────────┐
                        │  Detections  │
                        │  + Metadata  │
                        └──────────────┘
```

## Troubleshooting

### Pod not starting
```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name>
```

### Service not accessible
```bash
kubectl get svc
kubectl describe svc object-detection-service
```

### HPA not working
```bash
# Ensure metrics-server is running
kubectl get pods -n kube-system | grep metrics-server

# Check HPA status
kubectl describe hpa object-detection-hpa
```

## Performance Notes

- YOLOv11-nano is optimized for speed while maintaining good accuracy
- Average inference time: 50-100ms per image (CPU)
- Average inference time: 10-30ms per image (GPU)
- Supports COCO dataset classes (80 classes including person, car, etc.)

## Future Enhancements

- [ ] Add Redis caching for repeated detections
- [ ] Implement WebSocket for real-time streaming
- [ ] Add support for custom trained models
- [ ] Implement detection filtering by class
- [ ] Add tracking across frames


