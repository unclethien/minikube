# Object Detection Component - Quick Reference

## 🚀 One-Line Deployment
```bash
./deploy.sh
```

## 📋 Common Commands

### Deployment
```bash
# Deploy everything
kubectl apply -f k8s/

# Deploy specific components
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

### Monitoring
```bash
# Check pod status
kubectl get pods -l app=object-detection

# View logs (live)
kubectl logs -l app=object-detection -f

# Check HPA status
kubectl get hpa object-detection-hpa

# View resource usage
kubectl top pods -l app=object-detection

# Describe pod (troubleshooting)
kubectl describe pod <pod-name>
```

### Testing
```bash
# Get service URL
minikube service object-detection-service --url

# Test with image
python test_client.py $(minikube service object-detection-service --url) test.jpg

# Test health endpoint
curl $(minikube service object-detection-service --url)/health

# Test model info
curl $(minikube service object-detection-service --url)/info
```

### Scaling
```bash
# Manual scaling
kubectl scale deployment object-detection --replicas=3

# Check HPA
kubectl get hpa -w

# Describe HPA
kubectl describe hpa object-detection-hpa
```

### Cleanup
```bash
# Remove everything
./cleanup.sh

# Or manually
kubectl delete -f k8s/
```

## 🔧 Troubleshooting

### Pod not starting
```bash
kubectl describe pod <pod-name>
kubectl logs <pod-name>
```

### Service not accessible
```bash
kubectl get svc
kubectl describe svc object-detection-service
minikube service list
```

### HPA not working
```bash
# Check metrics-server
kubectl get pods -n kube-system | grep metrics-server

# Enable if needed
minikube addons enable metrics-server

# Check HPA events
kubectl describe hpa object-detection-hpa
```

### Out of memory
```bash
# Check resource usage
kubectl top pods

# Increase limits in k8s/deployment.yaml
# Then reapply: kubectl apply -f k8s/deployment.yaml
```

## 📊 API Endpoints

### POST /detect
**Upload single image for detection**
```bash
curl -X POST -F "image=@test.jpg" \
  http://<service-url>/detect
```

### POST /detect/batch
**Upload multiple images**
```bash
curl -X POST \
  -F "images=@test1.jpg" \
  -F "images=@test2.jpg" \
  http://<service-url>/detect/batch
```

### GET /health
**Health check**
```bash
curl http://<service-url>/health
```

### GET /info
**Model information**
```bash
curl http://<service-url>/info
```

## 🎯 Resource Specs

### CPU Deployment
- Request: 500m CPU, 1Gi RAM
- Limit: 2000m CPU, 3Gi RAM
- Replicas: 2-6 (auto-scaled)


## 📝 Configuration

Environment variables (in k8s/deployment.yaml):
- `PORT`: Server port (default: 8000)
- `CONFIDENCE_THRESHOLD`: Min confidence (default: 0.25)
- `IOU_THRESHOLD`: IOU for NMS (default: 0.45)
- `MAX_DETECTIONS`: Max detections (default: 300)

## 🔗 Integration Points

### Input: From Rescaling Component (Component 2)
- Receives: Rescaled images via POST /detect
- Format: multipart/form-data with image file

### Output: To Storage Component (Component 5)
- Sends: Detection metadata (JSON)
- Contains: Bounding boxes, class labels, confidence scores

## 📈 Performance Targets

- **Inference Time**: < 100ms per image (CPU)
- **Throughput**: 10-12 images/sec per pod
- **Startup Time**: < 120s (includes model download)
- **Memory Usage**: 800MB - 1.2GB per pod
- **CPU Usage**: 60-80% under load

## 🏷️ Labels and Selectors

Key labels:
- `app: object-detection`
- `component: video-processing`
- `workload: cpu-intensive`

Used for:
- Service selection
- Pod anti-affinity
- Monitoring/logging


