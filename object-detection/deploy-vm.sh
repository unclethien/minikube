#!/bin/bash
# Deployment script for VM

set -e

echo "================================================"
echo "Object Detection Component - VM Deployment"
echo "================================================"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed or not in PATH"
    exit 1
fi

echo "✓ Docker is available"
echo "✓ kubectl is available"
echo ""

# Build Docker image
echo "Building Docker image..."
docker build -t object-detection:latest .

if [ $? -eq 0 ]; then
    echo "✓ Docker image built successfully"
else
    echo "✗ Docker build failed"
    exit 1
fi
echo ""

# Deploy to Kubernetes
echo "Deploying to Kubernetes..."
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

echo "✓ Kubernetes resources applied"
echo ""

# Wait for pods
echo "Waiting for pods to be ready (this may take 1-2 minutes for model download)..."
kubectl wait --for=condition=ready pod -l app=object-detection --timeout=180s

if [ $? -eq 0 ]; then
    echo "✓ Pods are ready"
else
    echo "⚠ Pods may not be ready yet. Check with: kubectl get pods -l app=object-detection"
fi
echo ""

# Show deployment status
echo "================================================"
echo "Deployment Status"
echo "================================================"
kubectl get deployments -l app=object-detection
echo ""
kubectl get pods -l app=object-detection
echo ""
kubectl get svc object-detection-service
echo ""

# Try to apply HPA (may fail if metrics-server not available)
echo "Attempting to deploy Horizontal Pod Autoscaler..."
if kubectl apply -f k8s/hpa.yaml 2>&1; then
    echo "✓ HPA deployed"
    kubectl get hpa object-detection-hpa
else
    echo "⚠ HPA deployment skipped (metrics-server may not be available)"
fi
echo ""

echo "================================================"
echo "Deployment Complete!"
echo "================================================"
echo ""
echo "Test the service with:"
echo "  kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \\"
echo "    curl http://object-detection-service:8000/health"
echo ""
echo "View logs with:"
echo "  kubectl logs -l app=object-detection --tail=50 -f"
echo ""
echo "Monitor pods with:"
echo "  kubectl get pods -l app=object-detection -w"
echo ""


