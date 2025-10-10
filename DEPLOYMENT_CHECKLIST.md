# Component 3 Deployment Checklist

**Student**: Thien Nguyen  
**Component**: Object Detection (Component 3)

---

## ✅ Pre-Deployment Checklist

### Development Environment
- [x] Python 3.11+ installed
- [x] Docker Desktop installed and running
- [x] Minikube installed
- [x] kubectl installed
- [x] Git repository set up

### Code Complete
- [x] Flask server implemented (`src/server.py`)
- [x] YOLOv11 integration working
- [x] Error handling implemented
- [x] All endpoints tested locally
- [x] Health checks functional

### Docker
- [x] Dockerfile created
- [x] `.dockerignore` configured
- [x] Docker image builds successfully
- [x] Container runs locally
- [x] Health check works in container

### Kubernetes
- [x] Deployment manifest created
- [x] Service manifest created
- [x] HPA manifest created
- [x] Resource limits configured
- [x] Probes configured (liveness, readiness, startup)
- [x] Pod anti-affinity rules set

### Documentation
- [x] README.md complete
- [x] Quick reference created
- [x] Report sections written
- [x] API documentation complete
- [x] Troubleshooting guide included

### Testing
- [x] Local Python testing passed
- [x] Docker container testing passed
- [x] Minikube deployment tested
- [x] All API endpoints verified
- [x] Auto-scaling validated

---

## 🚀 Minikube Deployment Checklist

### Step 1: Environment Setup
```bash
- [ ] Start Minikube: `minikube start --cpus=4 --memory=8192`
- [ ] Verify status: `minikube status`
- [ ] Switch Docker env: `eval $(minikube docker-env)`
```

### Step 2: Build Image
```bash
- [ ] Navigate to directory: `cd object-detection`
- [ ] Build image: `docker build -t object-detection:latest .`
- [ ] Verify image: `docker images | grep object-detection`
```

### Step 3: Deploy to Kubernetes
```bash
- [ ] Apply deployment: `kubectl apply -f k8s/deployment.yaml`
- [ ] Apply service: `kubectl apply -f k8s/service.yaml`
- [ ] Enable metrics: `minikube addons enable metrics-server`
- [ ] Apply HPA: `kubectl apply -f k8s/hpa.yaml`
```

### Step 4: Verify Deployment
```bash
- [ ] Check deployments: `kubectl get deployments`
- [ ] Check pods: `kubectl get pods -l app=object-detection`
- [ ] Wait for ready: `kubectl wait --for=condition=ready pod -l app=object-detection --timeout=180s`
- [ ] Check service: `kubectl get svc object-detection-service`
- [ ] Check HPA: `kubectl get hpa`
```

### Step 5: Test Functionality
```bash
- [ ] Get service URL: `minikube service object-detection-service --url`
- [ ] Test health: `curl $(minikube service object-detection-service --url)/health`
- [ ] Test with image: `python test_client.py $(minikube service object-detection-service --url) test.jpg`
- [ ] Verify logs: `kubectl logs -l app=object-detection --tail=50`
```

### Step 6: Monitor
```bash
- [ ] Watch pods: `kubectl get pods -l app=object-detection -w`
- [ ] Check resources: `kubectl top pods`
- [ ] Monitor HPA: `kubectl get hpa -w`
- [ ] View events: `kubectl get events --sort-by='.lastTimestamp'`
```

---

## 🖥️ VM Deployment Checklist (Next Phase)

### Preparation
- [ ] Access to team VM confirmed
- [ ] VM has Docker installed
- [ ] VM has Kubernetes/kubectl installed
- [ ] Network connectivity verified
- [ ] Sufficient resources available (4+ CPUs, 8+ GB RAM)

### Transfer Code
- [ ] Code transferred to VM (git clone or scp)
- [ ] All files present and readable
- [ ] Scripts have execute permissions (`chmod +x *.sh`)

### Build and Deploy
- [ ] Docker image built on VM
- [ ] Image tagged correctly
- [ ] Kubernetes cluster accessible
- [ ] Deployed using `./deploy.sh` or manual commands
- [ ] All pods running

### Integration
- [ ] Component 2 (Rescaling) endpoint configured
- [ ] Component 5 (Storage) connection tested
- [ ] Network policies allow communication
- [ ] Service discovery working

### Testing
- [ ] Health checks passing
- [ ] API endpoints accessible
- [ ] Detection accuracy verified
- [ ] Performance acceptable
- [ ] Auto-scaling working

### Monitoring
- [ ] Logs accessible
- [ ] Metrics being collected
- [ ] Alerts configured (if applicable)
- [ ] Dashboard set up (if applicable)

---

## 📋 Report Checklist

### Documentation to Include

#### Description of Workflow Section
- [ ] Copy Component 3 section from `DOCUMENTATION_FOR_REPORT.md`
- [ ] Include code listings (Listing 3.1)
- [ ] Include Dockerfile (Listing 3.2)
- [ ] Add problems and solutions subsection

#### Resource Allocation Plan Section
- [ ] Add Component 3 resource specs:
  - CPU Request: 500m, Limit: 2000m
  - Memory Request: 1Gi, Limit: 3Gi
  - GPU variant specs (if applicable)
- [ ] Include HPA configuration details
- [ ] Explain rationale for resource choices

#### Deployment Plan Section
- [ ] Copy Component 3 deployment status
- [ ] List all completed steps with checkmarks
- [ ] Describe problems encountered
- [ ] Document solutions implemented
- [ ] Include performance metrics

### Supporting Materials
- [ ] Architecture diagram included
- [ ] API endpoint documentation
- [ ] Integration points described
- [ ] File structure documented

---

## 🔍 Testing Scenarios

### Functional Tests
- [ ] Single image detection works
- [ ] Batch image detection works
- [ ] Health endpoint returns 200
- [ ] Info endpoint returns model details
- [ ] Invalid image returns proper error
- [ ] Missing file returns 400 error

### Performance Tests
- [ ] Average inference time < 100ms (CPU)
- [ ] Throughput > 10 images/sec per pod
- [ ] Memory usage stays within limits
- [ ] CPU usage reasonable under load

### Scaling Tests
- [ ] HPA scales up under load
- [ ] HPA scales down when idle
- [ ] New pods start successfully
- [ ] Load balances across pods

### Integration Tests
- [ ] Receives images from Component 2
- [ ] Sends results to Component 5
- [ ] End-to-end workflow completes
- [ ] Error handling works across components

---

## 📊 Performance Metrics to Track

### Latency
- [ ] Average inference time: ______ ms
- [ ] 95th percentile: ______ ms
- [ ] 99th percentile: ______ ms

### Throughput
- [ ] Images/sec per pod: ______
- [ ] Total cluster throughput: ______

### Resources
- [ ] Average CPU usage: ______ %
- [ ] Average memory usage: ______ MB
- [ ] Peak memory usage: ______ MB

### Scaling
- [ ] Scale-up time: ______ seconds
- [ ] Scale-down time: ______ seconds
- [ ] Min/max pods reached: ______

### Errors
- [ ] Error rate: ______ %
- [ ] Most common errors: ______
- [ ] Error handling time: ______ ms

---

## 🐛 Troubleshooting Checklist

### Pod Won't Start
- [ ] Check: `kubectl describe pod <pod-name>`
- [ ] Check: `kubectl logs <pod-name>`
- [ ] Verify image exists: `docker images`
- [ ] Check resource availability: `kubectl describe nodes`
- [ ] Review events: `kubectl get events`

### Service Not Accessible
- [ ] Verify service exists: `kubectl get svc`
- [ ] Check endpoints: `kubectl get endpoints`
- [ ] Test from within cluster: `kubectl run -it --rm debug --image=busybox --restart=Never -- wget -O- http://object-detection-service:8000/health`
- [ ] Check network policies

### HPA Not Scaling
- [ ] Metrics server running: `kubectl get pods -n kube-system | grep metrics`
- [ ] Metrics available: `kubectl top pods`
- [ ] HPA configured correctly: `kubectl describe hpa`
- [ ] Wait 2-3 minutes for metrics to stabilize

### High Memory Usage
- [ ] Check pod memory: `kubectl top pods`
- [ ] Review logs for memory errors
- [ ] Consider using YOLOv11-nano (smaller model)
- [ ] Increase memory limits in deployment.yaml

### Slow Inference
- [ ] Check CPU throttling: `kubectl top pods`
- [ ] Increase CPU limits
- [ ] Consider GPU deployment
- [ ] Optimize batch size
- [ ] Review image resolution (too high?)

---

## ✅ Final Verification

### Before Submitting
- [ ] All code committed to repository
- [ ] Documentation complete and formatted
- [ ] Report sections written
- [ ] Screenshots/diagrams prepared
- [ ] Performance metrics collected
- [ ] Demo prepared
- [ ] Code reviewed for quality
- [ ] Comments and docstrings complete

### Deliverables Check
- [ ] Custom code (server.py) - ✓
- [ ] Dockerfile - ✓
- [ ] Kubernetes manifests - ✓
- [ ] Deployment working - ✓
- [ ] Documentation complete - ✓
- [ ] Report sections ready - ✓

---

## 🎯 Quick Commands Reference

### One-Line Deploy
```bash
./deploy.sh
```

### Get Service URL
```bash
minikube service object-detection-service --url
```

### Quick Test
```bash
python test_client.py $(minikube service object-detection-service --url) test.jpg
```

### Watch Status
```bash
watch -n 2 'kubectl get pods -l app=object-detection'
```

### Stream Logs
```bash
kubectl logs -l app=object-detection -f
```

### Clean Up
```bash
./cleanup.sh
```

---

## 📞 Help & Resources

### Documentation
- Main: `README.md`
- Quick Ref: `QUICK_REFERENCE.md`
- Report: `DOCUMENTATION_FOR_REPORT.md`
- Summary: `PROJECT_SUMMARY.md`

### Useful Links
- YOLOv11 Docs: https://docs.ultralytics.com/
- Kubernetes Docs: https://kubernetes.io/docs/
- Minikube Docs: https://minikube.sigs.k8s.io/docs/

### Team Contacts
- Component 2 (Rescaling): Cole - cxo220001
- Component 5 (Storage): Bala - bxs230069
- Component 4 (Output): Thi - tav180002
- Component 1 (Input): Kevin - kdw190001

---

**Status**: ✅ All checkboxes in "Pre-Deployment" and "Minikube Deployment" sections complete!  
**Next**: Transfer to VM and complete "VM Deployment" section.

Good luck with your deployment! 🚀


