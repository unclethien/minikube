#!/bin/bash
# Quick deployment script for base64 fix

set -e

echo "==================================================================="
echo "Deploying Base64 Fix + Debug Logging to K3s Cluster"
echo "==================================================================="

# Step 1: Transfer to node 102
echo ""
echo "[1/4] Transferring object-detection.tar to node 102..."
scp object-detection.tar dxn210021@csa-6343-102.utdallas.edu:~/
echo "✅ Transfer complete"

# Step 2: SSH to node 102 and deploy
echo ""
echo "[2/4] Deploying to K3s cluster..."
ssh dxn210021@csa-6343-102.utdallas.edu << 'ENDSSH'
set -e

# Transfer to worker 104
echo "  → Transferring to worker node 104..."
scp object-detection.tar dxn210021@csa-6343-104.utdallas.edu:/tmp/

# Import on worker 104
echo "  → Importing image on worker node 104..."
ssh dxn210021@csa-6343-104.utdallas.edu "sudo k3s ctr images import /tmp/object-detection.tar && rm /tmp/object-detection.tar"

# Clean up master
echo "  → Cleaning up master node..."
rm ~/object-detection.tar

# Restart deployment
echo "  → Restarting deployment..."
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml rollout restart deployment object-detection

# Wait for rollout
echo "  → Waiting for rollout to complete..."
sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml rollout status deployment object-detection --timeout=120s

echo "✅ Deployment complete"
ENDSSH

echo ""
echo "[3/4] Watching logs for debug output..."
echo "Looking for:"
echo "  - [DEBUG] /detect/batch request received from..."
echo "  - [DEBUG] Request files: [...]"
echo "  - [DEBUG] Files decoded successfully: [...]"
echo "  - [INFO] Decoded base64-encoded image: ..."
echo ""
echo "Press Ctrl+C to stop watching logs"
echo ""

# Watch logs
ssh dxn210021@csa-6343-102.utdallas.edu "sudo kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml logs -f -l app=object-detection --tail=50 | grep -E 'DEBUG|ERROR|INFO|Decoded base64'"

echo ""
echo "==================================================================="
echo "Deployment Complete!"
echo "==================================================================="
