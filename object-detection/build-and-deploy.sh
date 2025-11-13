#!/bin/bash
# Complete build and deployment workflow for object-detection service
# Run this on your Mac

set -e  # Exit on error

echo "=== Step 1: Build Optimized Docker Image ==="
docker build --platform linux/amd64 -t object-detection:latest .

echo ""
echo "=== Step 2: Save Image as TAR ==="
docker save object-detection:latest -o object-detection.tar

echo ""
echo "=== Step 3: Check TAR Size ==="
ls -lh object-detection.tar

echo ""
echo "=== Step 4: Transfer to Worker Node (104) ==="
echo "Transferring to csa-6343-104.utdallas.edu:/tmp/"
scp object-detection.tar txn200002@csa-6343-104.utdallas.edu:/tmp/

echo ""
echo "=== Step 5: Import on Worker Node (104) ==="
echo "Importing image into containerd..."
ssh txn200002@csa-6343-104.utdallas.edu 'sudo ctr -n k8s.io images import /tmp/object-detection.tar && sudo ctr -n k8s.io images ls | grep object-detection'

echo ""
echo "=== Step 6: Deploy from Control Plane (102) ==="
echo "Now SSH to node 102 and run:"
echo "  cd /path/to/minikube/object-detection"
echo "  kubectl apply -f k8s/deployment.yaml"
echo "  kubectl rollout status deployment/object-detection"
echo ""
echo "Or run the redeploy.sh script on node 102"
