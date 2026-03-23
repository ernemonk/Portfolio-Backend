#!/bin/bash

echo "🚀 Starting Trading OS Backend Services..."

# Backup original docker-compose.yml if not already backed up
if [ ! -f docker-compose.yml.gpu-backup ]; then
    cp docker-compose.yml docker-compose.yml.gpu-backup
fi

# Try starting with GPU support
echo "🎮 Attempting to start with NVIDIA GPU support..."
if docker-compose up -d 2>&1 | tee /tmp/docker-start.log; then
    if ! grep -q "nvidia-container-cli" /tmp/docker-start.log; then
        echo "✅ All services started successfully (with GPU if available)"
        docker-compose ps
        exit 0
    fi
fi

echo ""
echo "⚠️  GPU startup failed - retrying without NVIDIA GPU support..."
echo ""

# Stop and remove the problematic container
docker-compose stop local_ai 2>/dev/null || true
docker-compose rm -f local_ai 2>/dev/null || true

# Remove GPU config from docker-compose.yml
echo "📝 Temporarily removing GPU configuration..."
sed -i.tmp '/# Optional GPU support/,/capabilities: \[gpu\]/d' docker-compose.yml

# Start local_ai without GPU
echo "🔄 Starting Local AI service without GPU..."
if docker-compose up -d local_ai; then
    echo "✅ All services started successfully (CPU only)"
    docker-compose ps
    echo ""
    echo "💡 GPU support has been disabled. To re-enable:"
    echo "   cp docker-compose.yml.gpu-backup docker-compose.yml"
    exit 0
else
    echo "❌ Failed to start Local AI service"
    echo "Restoring original configuration..."
    cp docker-compose.yml.gpu-backup docker-compose.yml
    exit 1
fi
