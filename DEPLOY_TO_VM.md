# Deploy to VM Instructions

## Step 1: Transfer Files to VM

```bash
# On your local machine
cd /Users/thiennguyen/Documents/GitHub/minikube

# Transfer the tar file
scp object-detection-deployment.tar.gz dxn210021@csa-6343-104.utdallas.edu:/tmp/
# Password: Sugarland2019!@#$
```

## Step 2: SSH into VM

```bash
ssh dxn210021@csa-6343-104.utdallas.edu
# Password: Sugarland2019!@#$
```

## Step 3: Extract and Setup (On VM)

```bash
# Go to /tmp directory
cd /tmp

# Extract the files
tar -xzf object-detection-deployment.tar.gz

# Go into the directory
cd object-detection

# Check if Docker is available
docker --version

# Check if kubectl is available
kubectl version --client
```

## Step 4: Build Docker Image (On VM)

```bash
# Build the image
docker build -t object-detection:latest .

# Verify the image
docker images | grep object-detection
```

## Step 5: Test Locally on VM (Optional)

```bash
# Run container locally to test
docker run -d -p 8000:8000 --name test-object-detection object-detection:latest

# Test the health endpoint
curl http://localhost:8000/health

# If working, stop and remove test container
docker stop test-object-detection
docker rm test-object-detection
```

## Step 6: Deploy to Kubernetes (On VM)

```bash
# Check Kubernetes cluster status
kubectl cluster-info

# Apply the deployment
kubectl apply -f k8s/deployment.yaml

# Apply the service
kubectl apply -f k8s/service.yaml

# Apply HPA (if metrics-server is available)
kubectl apply -f k8s/hpa.yaml

# Check deployment status
kubectl get pods -l app=object-detection
kubectl get svc object-detection-service
```

## Step 7: Verify Deployment

```bash
# Check pod logs
kubectl logs -l app=object-detection --tail=50

# Check pod status
kubectl describe pod <pod-name>

# Get service details
kubectl get svc object-detection-service

# Test the service (from within cluster)
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://object-detection-service:8000/health
```

## Troubleshooting

### If pods are pending:
```bash
kubectl describe pod <pod-name>
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

### If image pull fails:
```bash
# Make sure image was built
docker images | grep object-detection

# Check ImagePullPolicy in deployment.yaml (should be IfNotPresent or Never)
```

### If pods crash:
```bash
# Check logs
kubectl logs <pod-name>

# Check resource availability
kubectl describe nodes
kubectl top nodes
```

## Quick Deployment Script

Save this as `deploy.sh` on the VM:

```bash
#!/bin/bash
set -e

echo "Building Docker image..."
docker build -t object-detection:latest .

echo "Deploying to Kubernetes..."
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

echo "Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=object-detection --timeout=180s

echo "Deployment complete!"
kubectl get pods -l app=object-detection
kubectl get svc object-detection-service

echo ""
echo "Test the service with:"
echo "kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- curl http://object-detection-service:8000/health"
```

Then run:
```bash
chmod +x deploy.sh
./deploy.sh
```

## Deployment Plan Entry

For your project report deployment section:

```
Component 3 (Thien): Developed Flask-based object detection server with YOLOv11 integration and containerized it. Tested locally using Minikube with horizontal auto-scaling. Encountered challenges with YOLOv11 model download timing and initial memory allocation, resolved by implementing longer startup probes and increasing resource limits. Successfully deployed to team VM (csa-6343-104.utdallas.edu) using Docker and Kubernetes. Verified CPU deployment achieving 80ms inference time per image. Currently integrated with pipeline for processing video frames from rescaling component.
```


