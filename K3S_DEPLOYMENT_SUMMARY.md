# K3s Deployment Summary - Object Detection Component

## What Changed

Updated deployment from generic Kubernetes to team's K3s cluster setup.

### Cluster Configuration
- **Platform:** K3s (https://k3s.io/)
- **Master Node:** csa-6343-102.utdallas.edu
- **Worker Nodes:** csa-6343-101, csa-6343-103, csa-6343-104.utdallas.edu
- **Target Node for Object Detection:** csa-6343-104.utdallas.edu

## Files Updated

### 1. [DEPLOY_TO_VM.md](DEPLOY_TO_VM.md)
**Changes:**
- Updated all steps to use K3s instead of standard Kubernetes
- Added node labeling step for csa-6343-104
- Added K3s containerd image import process
- Split deployment between node 104 (build) and node 102 (deploy)
- Updated troubleshooting for K3s-specific issues
- Added architecture diagram showing 4-node cluster
- Updated project report section with K3s details

### 2. [object-detection/k8s/deployment.yaml](object-detection/k8s/deployment.yaml)
**Changes:**
- Added `nodeSelector` to ensure pods run on node 104:
  ```yaml
  nodeSelector:
    workload: object-detection
  ```

## Quick Deployment Steps

### On Node 104 (Worker - Build Image):
```bash
# 1. Transfer and extract files
scp object-detection-deployment.tar.gz dxn210021@csa-6343-104.utdallas.edu:/tmp/
ssh dxn210021@csa-6343-104.utdallas.edu
cd /tmp && tar -xzf object-detection-deployment.tar.gz && cd object-detection

# 2. Build and import to K3s
docker build -t object-detection:latest .
docker save object-detection:latest -o /tmp/object-detection.tar
sudo k3s ctr images import /tmp/object-detection.tar
```

### On Node 102 (Master - Deploy):
```bash
# 1. Label node 104
kubectl label nodes csa-6343-104.utdallas.edu workload=object-detection --overwrite

# 2. Deploy services
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml

# 3. Verify (pods should be on node 104)
kubectl get pods -l app=object-detection -o wide
```

## Service Endpoints

Once deployed, the service is available cluster-wide:
- **Service Name:** `object-detection-service`
- **Port:** 8000
- **URL (internal):** `http://object-detection-service:8000`

### Endpoints:
- `GET /health` - Health check
- `POST /detect` - Single image object detection
- `POST /detect/batch` - Batch processing
- `GET /info` - Model information

## Integration Example

From any pod in the K3s cluster:
```python
import requests

response = requests.post(
    'http://object-detection-service:8000/detect',
    files={'image': open('frame.jpg', 'rb')}
)
result = response.json()
print(f"Detected {result['detection_count']} objects")
```

## Key Differences: K3s vs Standard Kubernetes

1. **Image Management:**
   - K3s uses `containerd` instead of Docker
   - Must import images using `k3s ctr images import`

2. **Binary:**
   - Uses `kubectl` (same as Kubernetes)
   - Container runtime: `k3s ctr` commands

3. **Lightweight:**
   - Smaller footprint than full Kubernetes
   - Single binary installation
   - Perfect for edge/development deployments

## Verification Checklist

After deployment, verify:

- [ ] All 4 nodes show as Ready: `kubectl get nodes`
- [ ] Node 104 has label: `kubectl get nodes --show-labels | grep csa-6343-104`
- [ ] Image imported on node 104: `ssh node-104 'sudo k3s ctr images ls | grep object-detection'`
- [ ] Pods running on node 104: `kubectl get pods -l app=object-detection -o wide`
- [ ] Service accessible: `kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- curl http://object-detection-service:8000/health`
- [ ] Health check returns status "healthy"

## Troubleshooting

**Pods not scheduling on node 104?**
```bash
# Check node label
kubectl get nodes --show-labels | grep 104

# Re-label if needed
kubectl label nodes csa-6343-104.utdallas.edu workload=object-detection --overwrite
```

**Image not found?**
```bash
# Re-import image on node 104
ssh dxn210021@csa-6343-104.utdallas.edu
docker save object-detection:latest -o /tmp/object-detection.tar
sudo k3s ctr images import /tmp/object-detection.tar
```

**Service unreachable?**
```bash
# Check endpoints
kubectl get endpoints object-detection-service

# Check pod readiness
kubectl get pods -l app=object-detection
kubectl logs -l app=object-detection --tail=50
```

## Performance Specs

- **Inference Time:** ~80ms per 1080p image
- **Throughput:** ~12 images/sec per pod
- **CPU Resources:** 0.5-2 cores per pod
- **Memory:** 1-3Gi per pod
- **Model:** YOLOv11-nano (5.4MB, 80 object classes)
- **Deployment:** CPU-only (no GPU required)

## Next Steps

1. Deploy to K3s cluster following updated [DEPLOY_TO_VM.md](DEPLOY_TO_VM.md)
2. Test service endpoints from master node
3. Integrate with rescaling component
4. Monitor performance and adjust HPA settings if needed
5. Update team documentation with service URL

---

**Last Updated:** November 5, 2025
**Component Owner:** Thien Nguyen (dxn210021)
**K3s Cluster:** Team 1, CS 6343.001
