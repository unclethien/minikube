# Object Detection Component - Quick Reference

## 🏗️ K3s Cluster Setup
- **Master Node**: csa-6343-102.utdallas.edu
- **Target Node**: csa-6343-104.utdallas.edu
- **Service URL**: `http://object-detection-service:8000` (internal)

## 🚀 Quick Deployment to K3s

### On Node 104 (Build):
```bash
cd /tmp/object-detection
docker build -t object-detection:latest .
docker save object-detection:latest -o /tmp/object-detection.tar
sudo k3s ctr images import /tmp/object-detection.tar
```

### On Master Node 102 (Deploy):
```bash
kubectl label nodes csa-6343-104.utdallas.edu workload=object-detection --overwrite
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
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

# Check deployment on correct node
kubectl get pods -l app=object-detection -o wide
# Should show NODE: csa-6343-104.utdallas.edu
```

### Monitoring
```bash
# Check pod status (with node info)
kubectl get pods -l app=object-detection -o wide

# View logs (live)
kubectl logs -l app=object-detection -f

# Check HPA status
kubectl get hpa object-detection-hpa

# View resource usage
kubectl top pods -l app=object-detection
kubectl top nodes

# Describe pod (troubleshooting)
kubectl describe pod <pod-name>
```

### Testing
```bash
# Port-forward from master node
kubectl port-forward svc/object-detection-service 8000:8000

# In another terminal, test
curl http://localhost:8000/health
python test_client.py http://localhost:8000 test.jpg

# Or test from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://object-detection-service:8000/health
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
# Check pod events and status
kubectl describe pod <pod-name>
kubectl logs <pod-name>

# Check if on correct node
kubectl get pods -l app=object-detection -o wide
# Should show NODE: csa-6343-104.utdallas.edu
```

### Pod not scheduled to node 104
```bash
# Check node label
kubectl get nodes --show-labels | grep csa-6343-104

# Re-label if needed
kubectl label nodes csa-6343-104.utdallas.edu workload=object-detection --overwrite
```

### Image not found (K3s)
```bash
# Check image on node 104
ssh dxn210021@csa-6343-104.utdallas.edu
sudo k3s ctr images ls | grep object-detection

# Re-import if missing
docker save object-detection:latest -o /tmp/object-detection.tar
sudo k3s ctr images import /tmp/object-detection.tar
```

### Service not accessible
```bash
# Check service and endpoints
kubectl get svc object-detection-service
kubectl get endpoints object-detection-service

# Port-forward for testing
kubectl port-forward svc/object-detection-service 8000:8000
```

### HPA not working
```bash
# Check metrics-server
kubectl get pods -n kube-system | grep metrics-server

# Check HPA events
kubectl describe hpa object-detection-hpa

# Check pod metrics
kubectl top pods -l app=object-detection
```

### Out of memory
```bash
# Check resource usage
kubectl top pods -l app=object-detection
kubectl describe pod <pod-name> | grep -A 5 Limits

# Increase limits in k8s/deployment.yaml
# Then reapply: kubectl apply -f k8s/deployment.yaml
```

### YOLOv11 model download slow
```bash
# Check pod logs for download progress
kubectl logs <pod-name> | grep -i download

# Model downloads on first run (~5.4MB, may take 30-60s)
# Startup probe allows up to 2 minutes for initialization
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

Node labels (for scheduling):
- Node 104: `workload=object-detection`

Used for:
- Service selection
- Node scheduling (nodeSelector)
- Pod anti-affinity
- Monitoring/logging

## 📦 K3s Notes

**Image Management:**
- K3s uses containerd (not Docker daemon)
- Images must be imported: `sudo k3s ctr images import <tar-file>`
- Check images: `sudo k3s ctr images ls`

**Node Scheduling:**
- Pods scheduled to node 104 via `nodeSelector`
- Label must be set: `kubectl label nodes csa-6343-104.utdallas.edu workload=object-detection`

**Service Access:**
- Internal: `http://object-detection-service:8000`
- External testing: Use `kubectl port-forward`

## 📚 Full Documentation

- Complete deployment guide: [DEPLOY_TO_VM.md](../DEPLOY_TO_VM.md)
- K3s cluster setup: [K3S_DEPLOYMENT_SUMMARY.md](../K3S_DEPLOYMENT_SUMMARY.md)
- Detailed README: [README.md](README.md)


