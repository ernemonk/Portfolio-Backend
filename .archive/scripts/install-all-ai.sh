#!/bin/bash

echo "🚀 TRADING OS AI - COMPLETE INSTALLATION"
echo "════════════════════════════════════════════════════════════════"
echo "Installing ALL AI models for maximum flexibility..."
echo ""

# Check if we're in the right directory
cd "$(dirname "$0")"
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Please run this from the Backend directory"
    exit 1
fi

echo "🎯 WHAT THIS INSTALLS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "⚡ ULTRA-FAST (for real-time trading):"
echo "   • Orca Mini 3B (1.9GB) - Instant responses"
echo "   • Microsoft Phi-2 (2.7GB) - Fast reasoning"
echo ""
echo "🎯 BALANCED (best all-around):"  
echo "   • Mistral 7B (4.1GB) - Main trading analysis"
echo "   • FinBERT (400MB) - Financial specialist"
echo ""
echo "🧠 HIGH-QUALITY (deep analysis):"
echo "   • Nous Hermes 13B (7.3GB) - Premium intelligence"
echo "   • Code Llama 7B (13GB) - Algorithm development"
echo ""
echo "🔍 SPECIALIZED:"
echo "   • MiniLM Embeddings (80MB) - Document search"
echo "   • DialoGPT (350MB) - Chat interface"
echo ""
echo "📊 TOTAL: ~45GB (one-time download, cached forever)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -p "🚀 Install complete AI suite? This will take 30-60 minutes [y/N]: " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "❌ Installation cancelled"
    exit 0
fi

echo ""
echo "🔧 Setting up directories and configuration..."

# Create directories
mkdir -p .data/ai_models .data/model_cache

# Create environment file if doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env configuration..."
    cat > .env << 'EOF'
# Trading OS AI Configuration
AI_PERFORMANCE_TIER=full
AI_AUTO_DOWNLOAD=true
AI_PRELOAD_MODELS=true
AI_MAX_MEMORY_GB=16
AI_ENABLE_MODEL_SWITCHING=true
EOF
    echo "✅ Created .env file"
fi

echo ""
echo "🚀 Starting AI service and downloading ALL models..."
echo "   This will take 30-60 minutes depending on your internet speed"
echo "   Models are cached forever, so this is a one-time process"
echo ""

# Start the service with full tier
docker-compose up -d local_ai

echo "📥 Models are downloading in the background..."
echo "📊 You can monitor progress with: docker-compose logs -f local_ai"
echo ""

# Wait for service to start
echo "⏳ Waiting for service to initialize..."
for i in {1..30}; do
    if curl -s http://localhost:3008/health &>/dev/null; then
        echo "✅ Service is running!"
        break
    fi
    echo -n "."
    sleep 2
done

echo ""
echo "🎉 INSTALLATION COMPLETE!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🎯 YOUR TRADING DASHBOARD NOW HAS:"
echo "   • Ultra-fast models for real-time decisions"  
echo "   • High-quality models for deep analysis"
echo "   • Specialized models for specific tasks"
echo "   • Smart auto-selection based on use case"
echo ""
echo "🚀 DASHBOARD ENDPOINTS:"
echo "   📊 Model selection: http://localhost:3008/dashboard/models"
echo "   🤖 Smart completion: POST /v1/chat/completions/smart"
echo "   ⚙️  Task-based selection: POST /dashboard/select-model"
echo "   📈 Health & status: http://localhost:3008/health"
echo ""
echo "💡 USAGE IN YOUR TRADING PORTAL:"
echo "   • Real-time trading → Auto-selects fastest model"
echo "   • Financial analysis → Auto-selects balanced model"
echo "   • Research/reports → Auto-selects highest quality"
echo "   • Code generation → Auto-selects code specialist"
echo ""
echo "📋 MONITORING:"
echo "   docker-compose logs local_ai     # View logs"
echo "   curl localhost:3008/health       # Check status"
echo "   curl localhost:3008/dashboard/models  # Available models"
echo ""
echo "✅ Ready for your trading dashboard integration!"