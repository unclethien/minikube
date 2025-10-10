# GPU Deployment Guide for Component 3

**Component**: Object Detection (Component 3)  
**VM**: GPU-Enabled Node  
**GPU**: NVIDIA GPU (confirmed)

---

## 🎯 Quick Deploy (On GPU VM)

```bash
# 1. Label your GPU node
kubectl label nodes <your-vm-hostname> gpu=true
kubectl label nodes <your-vm-hostname> workload=gpu-intensive

# 2. Apply GPU taint (prevents non-GPU workloads)
kubectl taint nodes <your-vm-hostname> gpu=true:NoSchedule

# 3. Deploy GPU-optimized version
cd object-detection
kubectl apply -f k8s/gpu-deployment.yaml
kubectl apply -f k8s/service.yaml

# 4. Verify GPU pod is running
kubectl get pods -l app=object-detection-gpu -o wide
kubectl logs -l app=object-detection-gpu
```

---

## 📋 Pre-Deployment Checklist

### Verify GPU is Available
```bash
# Check if NVIDIA GPU is detected
nvidia-smi

# Should show something like:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI 535.xx.xx    Driver Version: 535.xx.xx    CUDA Version: 12.x   |
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |===============================+======================+======================|
# |   0  Tesla T4            Off  | 00000000:00:04.0 Off |                    0 |
# | N/A   42C    P0    27W /  70W |      0MiB / 15360MiB |      0%      Default |
# +-------------------------------+----------------------+----------------------+
```

### Verify NVIDIA Docker Runtime
```bash
# Check if nvidia-container-runtime is installed
docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi

# Should show the same GPU info as above
```

### Verify Kubernetes GPU Plugin
```bash
# Check if NVIDIA device plugin is running
kubectl get pods -n kube-system | grep nvidia-device-plugin

# Check GPU resources are available
kubectl describe nodes | grep -A 5 "Allocatable"
# Should show: nvidia.com/gpu: 1
```

---

## 🔧 Step-by-Step Deployment

### Step 1: Prepare GPU Node

```bash
# Get your node name
kubectl get nodes

# Label the GPU node
export GPU_NODE=<your-node-name>
kubectl label nodes $GPU_NODE gpu=true
kubectl label nodes $GPU_NODE workload=gpu-intensive

# Taint the node (prevents non-GPU pods)
kubectl taint nodes $GPU_NODE gpu=true:NoSchedule

# Verify labels and taints
kubectl describe node $GPU_NODE | grep -A 3 "Labels:"
kubectl describe node $GPU_NODE | grep -A 3 "Taints:"
```

### Step 2: Deploy Object Detection with GPU

```bash
cd /path/to/object-detection

# Build Docker image (if not already built)
docker build -t object-detection:latest .

# Deploy GPU-optimized deployment
kubectl apply -f k8s/gpu-deployment.yaml

# Deploy service
kubectl apply -f k8s/service.yaml
```

### Step 3: Verify Deployment

```bash
# Check pod status
kubectl get pods -l app=object-detection-gpu

# Check pod is on GPU node
kubectl get pods -l app=object-detection-gpu -o wide

# Check GPU allocation
kubectl describe pod <pod-name> | grep -A 5 "Limits"
# Should show: nvidia.com/gpu: 1

# Check logs
kubectl logs -l app=object-detection-gpu --tail=50

# Should see:
# "Loading YOLOv11 model..."
# "Model loaded successfully!"
# "Starting Object Detection Server on port 8000"
```

### Step 4: Test GPU Utilization

```bash
# In one terminal, watch GPU usage
watch -n 1 nvidia-smi

# In another terminal, send test requests
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl -X POST -F "image=@/path/to/test.jpg" \
  http://object-detection-service:8000/detect

# You should see GPU utilization spike in nvidia-smi output
```

---

## 📊 Performance Validation

### Expected Metrics with GPU

```bash
# Test inference time
python test_client.py http://<service-url> test_image.jpg

# Expected output:
# ✓ Success!
# Detection count: X
# Inference time: ~15-25ms  ← Should be much faster than CPU (80ms)
```

### Monitor GPU Usage

```bash
# Real-time GPU monitoring
nvidia-smi dmon -s u

# Check GPU memory
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Expected: ~1GB VRAM used when processing
```

---

## 🐛 Troubleshooting

### Pod Stuck in Pending

```bash
# Check why pod is pending
kubectl describe pod <pod-name>

# Common issues:
# 1. Node not labeled: kubectl label nodes <node> gpu=true
# 2. No GPU available: Check nvidia-smi
# 3. GPU plugin not running: kubectl get pods -n kube-system | grep nvidia
```

### Pod Running but No GPU Access

```bash
# Check if pod can see GPU
kubectl exec -it <pod-name> -- python -c "import torch; print(torch.cuda.is_available())"

# Should output: True

# If False, check:
# 1. NVIDIA runtime: docker run --rm --gpus all nvidia/cuda nvidia-smi
# 2. Device plugin: kubectl logs -n kube-system <nvidia-device-plugin-pod>
```

### Poor Performance (No Speedup)

```bash
# Check if YOLO is actually using GPU
kubectl logs <pod-name> | grep -i cuda

# Send request and monitor GPU
# Terminal 1:
watch -n 0.5 nvidia-smi

# Terminal 2:
for i in {1..10}; do
  curl -X POST -F "image=@test.jpg" http://<service>/detect
done

# GPU utilization should spike to 70-90%
```

---

## 📝 Key Files for GPU Deployment

### **k8s/gpu-deployment.yaml** (Use This!)
```yaml
# Key sections:
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: gpu
            operator: In
            values:
            - "true"
  
  tolerations:
  - key: "gpu"
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
  
  resources:
    requests:
      nvidia.com/gpu: 1
    limits:
      nvidia.com/gpu: 1
```

### **k8s/service.yaml**
```yaml
# Service works for both CPU and GPU deployments
# Just update selector if using GPU deployment:
selector:
  app: object-detection-gpu  # or object-detection for CPU
```

---

## 🎯 Deployment Comparison

### CPU Deployment (Local Testing)
```bash
kubectl apply -f k8s/deployment.yaml  # CPU version
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

### GPU Deployment (Production VM) ⭐
```bash
kubectl apply -f k8s/gpu-deployment.yaml  # GPU version
kubectl apply -f k8s/service.yaml
# HPA optional - limited by GPU availability
```

---

## 📈 Expected Performance Gains

| Metric | CPU (Local) | GPU (VM) | Improvement |
|--------|-------------|----------|-------------|
| Inference Time | 80ms | 15-25ms | **3-5x faster** |
| Throughput | 12 img/sec | 35-50 img/sec | **3-4x higher** |
| Memory | 1-1.2GB RAM | 2-2.5GB RAM + 1GB VRAM | +1GB overhead |
| Latency (p95) | 120ms | 35ms | **3.4x faster** |

---

## 🚀 Quick Commands

### Deploy
```bash
kubectl label nodes <node> gpu=true workload=gpu-intensive
kubectl taint nodes <node> gpu=true:NoSchedule
kubectl apply -f k8s/gpu-deployment.yaml
kubectl apply -f k8s/service.yaml
```

### Monitor
```bash
watch nvidia-smi
kubectl logs -l app=object-detection-gpu -f
kubectl top pods
```

### Test
```bash
python test_client.py $(kubectl get svc object-detection-service -o jsonpath='{.spec.clusterIP}'):8000 test.jpg
```

### Cleanup
```bash
kubectl delete -f k8s/gpu-deployment.yaml
kubectl delete -f k8s/service.yaml
kubectl taint nodes <node> gpu=true:NoSchedule-
kubectl label nodes <node> gpu- workload-
```

---

## ✅ Deployment Checklist

- [ ] NVIDIA driver installed on VM
- [ ] `nvidia-smi` shows GPU
- [ ] Docker with NVIDIA runtime installed
- [ ] Kubernetes NVIDIA device plugin running
- [ ] Node labeled with `gpu=true`
- [ ] Node tainted with `gpu=true:NoSchedule`
- [ ] Docker image built
- [ ] GPU deployment applied
- [ ] Service applied
- [ ] Pod running on GPU node
- [ ] GPU visible inside pod (`torch.cuda.is_available()` = True)
- [ ] Test request completes successfully
- [ ] GPU utilization visible in `nvidia-smi`
- [ ] Performance matches expectations (15-25ms)

---

Good luck with your GPU deployment! 🎉🚀


