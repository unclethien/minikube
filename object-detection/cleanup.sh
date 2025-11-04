#!/bin/bash
# Cleanup script for Object Detection component

echo "Cleaning up Object Detection deployment..."

# Delete HPA
kubectl delete -f k8s/hpa.yaml --ignore-not-found=true

# Delete Service
kubectl delete -f k8s/service.yaml --ignore-not-found=true

# Delete Deployment
kubectl delete -f k8s/deployment.yaml --ignore-not-found=true

echo "Cleanup complete!"


