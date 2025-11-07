#!/bin/bash
set -e

echo "=== Object Detection K3s Deployment Script ==="
echo "Master Node: csa-6343-102.utdallas.edu"
echo "Target Node: csa-6343-104.utdallas.edu"
echo ""

# Verify cluster
echo "Step 1: Checking K3s cluster status..."
kubectl get nodes -o wide

# Build image
echo ""
echo "Step 2: Building Docker image on master node..."
docker build -t object-detection:latest .

# Distribute image to node 104≠
echo ""
echo "Step 3: Distributing image to node 104..."
docker save object-detection:latest -o /tmp/object-detection.tar
scp /tmp/object-detection.tar dxn210021@csa-6343-104.utdallas.edu:/tmp/
ssh dxn210021@csa-6343-104.utdallas.edu "sudo k3s ctr images import /tmp/object-detection.tar && rm /tmp/object-detection.tar"
rm /tmp/object-detection.tar
echo "✓ Image distributed successfully!"

# Label node 104
echo ""
echo "Step 4: Labeling node 104 for object detection workload..."
kubectl label nodes csa-6343-104.utdallas.edu workload=object-detection --overwrite

# Deploy
echo ""
echo "Step 5: Deploying to K3s cluster..."
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml 2>/dev/null || echo "HPA skipped (metrics-server may not be available)"

# Wait for pods
echo ""
echo "Step 6: Waiting for pods to be ready (may take 2-3 minutes for model download)..."
kubectl wait --for=condition=ready pod -l app=object-detection --timeout=180s || true

# Show status
echo ""
echo "=== Deployment Status ==="
kubectl get pods -l app=object-detection -o wide
kubectl get svc object-detection-service

echo ""
echo "=== Test the service ==="
echo "kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- curl http://object-detection-service:8000/health"
echo ""
echo "✓ Deployment complete!"
