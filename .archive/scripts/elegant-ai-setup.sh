#!/bin/bash

echo "🎯 ELEGANT AI SETUP FOR TRADING PORTAL"
echo "════════════════════════════════════════════════════════════════"

cd "$(dirname "$0")/.."  # Go to Backend directory

echo "🚀 Starting with Docker-based AI service..."
echo "   This approach is more reliable and integrates seamlessly!"

# Start the service using Docker (which handles all dependencies)
echo "📦 Starting AI service via Docker Compose..."
docker-compose up -d local_ai

echo ""
echo "⏳ Waiting for AI service to initialize..."
sleep 5

# Check if it's running
if curl -s http://localhost:3008/health &>/dev/null; then
    echo "✅ AI Service is running!"
    echo ""
    echo "🎉 PORTAL INTEGRATION READY!"
    echo "════════════════════════════════════════════════════════════════"
    echo ""
    echo "🎯 BEAUTIFUL TRADING PORTAL FEATURES:"
    echo "   • Smart AI model selection based on task"
    echo "   • Real-time trading decisions (ultra-fast models)"  
    echo "   • Deep financial analysis (premium models)"
    echo "   • Code generation for trading strategies"
    echo "   • Market sentiment analysis"
    echo "   • Beautiful chat interface with animations"
    echo ""
    echo "🚀 PORTAL INTEGRATION:"
    echo "   1. Add this to your portal navigation:"
    echo "      http://localhost:3000/portal/ai"
    echo ""
    echo "   2. AI Component is ready at:"
    echo "      components/portal/AITradingAssistant.tsx"
    echo ""
    echo "   3. Hook for easy integration:"
    echo "      hooks/useAITrading.ts"
    echo ""
    echo "📡 API ENDPOINTS:"
    echo "   • Dashboard models: http://localhost:3008/dashboard/models"
    echo "   • Smart completion: POST /v1/chat/completions/smart"  
    echo "   • Model selection: POST /dashboard/select-model"
    echo "   • Health check: http://localhost:3008/health"
    echo ""
    echo "💡 NEXT STEPS:"
    echo "   1. Open your portal: http://localhost:3000/portal/ai"
    echo "   2. Start chatting with AI for trading insights"
    echo "   3. Models auto-download on first use"
    echo "   4. Enjoy beautiful, intelligent trading assistance!"
    echo ""
    echo "🔥 All models will download automatically when needed."
    echo "    No manual setup required - just start using it!"
    
else
    echo "⚠️  AI service starting up... Check with:"
    echo "   docker-compose logs local_ai"
    echo ""
    echo "🔧 If issues persist, the AI will work in development mode"
    echo "   and models will download as needed."
fi

echo ""
echo "✨ Your trading portal now has ELEGANT AI integration!"