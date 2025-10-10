#!/bin/bash
# Deployment script for Object Detection component on Minikube

set -e

echo "======================================"
echo "Object Detection Component Deployment"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if minikube is running
echo "Checking Minikube status..."
if ! minikube status &> /dev/null; then
    echo -e "${YELLOW}Minikube is not running. Starting Minikube...${NC}"
    minikube start --cpus=4 --memory=8192
else
    echo -e "${GREEN}✓ Minikube is running${NC}"
fi
echo ""

# Switch to Minikube's Docker environment
echo "Configuring Docker to use Minikube's Docker daemon..."
eval $(minikube docker-env)
echo -e "${GREEN}✓ Docker environment configured${NC}"
echo ""

# Build Docker image
echo "Building Docker image..."
docker build -t object-detection:latest .
echo -e "${GREEN}✓ Docker image built successfully${NC}"
echo ""

# Deploy to Kubernetes
echo "Deploying to Kubernetes..."
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
echo -e "${GREEN}✓ Deployment and Service created${NC}"
echo ""

# Enable metrics server if not already enabled
echo "Enabling metrics-server addon..."
minikube addons enable metrics-server
echo -e "${GREEN}✓ Metrics server enabled${NC}"
echo ""

# Deploy HPA
echo "Deploying Horizontal Pod Autoscaler..."
kubectl apply -f k8s/hpa.yaml
echo -e "${GREEN}✓ HPA deployed${NC}"
echo ""

# Wait for pods to be ready
echo "Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=object-detection --timeout=180s
echo -e "${GREEN}✓ Pods are ready${NC}"
echo ""

# Display deployment status
echo "======================================"
echo "Deployment Status"
echo "======================================"
kubectl get deployments -l app=object-detection
echo ""
kubectl get pods -l app=object-detection
echo ""
kubectl get svc object-detection-service
echo ""
kubectl get hpa object-detection-hpa
echo ""

# Get service URL
echo "======================================"
echo "Service Information"
echo "======================================"
SERVICE_URL=$(minikube service object-detection-service --url)
echo -e "${GREEN}Service URL: ${SERVICE_URL}${NC}"
echo ""
echo "Test the service with:"
echo "  python test_client.py ${SERVICE_URL}"
echo ""
echo "View logs with:"
echo "  kubectl logs -l app=object-detection --tail=50 -f"
echo ""
echo "======================================"
echo -e "${GREEN}Deployment Complete!${NC}"
echo "======================================"


