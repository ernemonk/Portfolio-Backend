#!/bin/bash

# Trading OS AI Management Script
# YAML-driven model management for containerized deployment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

show_usage() {
    echo "🤖 Trading OS AI Management"
    echo "══════════════════════════════════════════════════════════════"
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start [tier]     Start AI service with specified tier (fast|balanced|quality)"
    echo "  stop            Stop AI service"
    echo "  restart [tier]  Restart with new tier"
    echo "  status          Show current status and configuration" 
    echo "  logs            Show service logs"
    echo "  models          List available models"
    echo "  switch <tier>   Switch performance tier"
    echo "  setup           Initial setup and configuration"
    echo ""
    echo "Performance Tiers:"
    echo "  fast            Ultra-fast models (4GB) - for development/testing"
    echo "  balanced        Best mix (8GB) - for production [DEFAULT]"
    echo "  quality         Highest quality (15GB) - for research/analysis"
    echo ""
    echo "Examples:"
    echo "  $0 start balanced    # Start with balanced tier"
    echo "  $0 switch fast       # Switch to fast tier"
    echo "  $0 status           # Check current status"
}

start_service() {
    local tier=${1:-balanced}
    
    echo "🚀 Starting Trading OS AI service with '$tier' tier..."
    
    case $tier in
        fast)
            docker-compose -f docker-compose.yml -f docker-compose.ai-fast.yml up -d local_ai
            ;;
        balanced)
            docker-compose up -d local_ai
            ;;
        quality)
            docker-compose -f docker-compose.yml -f docker-compose.ai-quality.yml up -d local_ai
            ;;
        *)
            echo "❌ Invalid tier: $tier. Use: fast, balanced, quality"
            exit 1
            ;;
    esac
    
    echo "✅ AI service started with '$tier' tier"
    echo "📡 Service available at: http://localhost:3008"
    echo "🔍 Health check: curl http://localhost:3008/health"
}

stop_service() {
    echo "⏹️  Stopping Trading OS AI service..."
    docker-compose stop local_ai
    echo "✅ AI service stopped"
}

restart_service() {
    local tier=${1:-balanced}
    echo "🔄 Restarting AI service with '$tier' tier..."
    stop_service
    start_service $tier
}

show_status() {
    echo "📊 Trading OS AI Status"
    echo "══════════════════════════════════════════════════════════════"
    
    if docker-compose ps local_ai | grep -q "Up"; then
        echo "✅ Service Status: Running"
        
        # Get current configuration
        local tier=$(docker-compose exec -T local_ai printenv AI_PERFORMANCE_TIER 2>/dev/null || echo "unknown")
        local memory=$(docker-compose exec -T local_ai printenv AI_MAX_MEMORY_GB 2>/dev/null || echo "unknown")
        local preload=$(docker-compose exec -T local_ai printenv AI_PRELOAD_MODELS 2>/dev/null || echo "unknown")
        
        echo "🎯 Performance Tier: $tier"
        echo "💾 Memory Limit: ${memory}GB"  
        echo "🔥 Preload Models: $preload"
        echo "📡 Endpoint: http://localhost:3008"
        
        # Try to get model info from API
        if curl -s http://localhost:3008/health &>/dev/null; then
            echo "🟢 Health Check: Passed"
        else
            echo "🟡 Health Check: Service starting..."
        fi
    else
        echo "❌ Service Status: Stopped"
    fi
}

show_logs() {
    echo "📋 Trading OS AI Logs"
    echo "══════════════════════════════════════════════════════════════"
    docker-compose logs -f local_ai
}

list_models() {
    echo "🤖 Available Models"
    echo "══════════════════════════════════════════════════════════════"
    
    if curl -s http://localhost:3008/models/info &>/dev/null; then
        curl -s http://localhost:3008/models/info | python3 -m json.tool
    else
        echo "❌ Service not running. Start with: $0 start"
    fi
}

switch_tier() {
    local new_tier=$1
    if [ -z "$new_tier" ]; then
        echo "❌ Please specify tier: fast, balanced, quality"
        exit 1
    fi
    
    echo "🔄 Switching to '$new_tier' tier..."
    restart_service $new_tier
}

setup_service() {
    echo "🛠️  Setting up Trading OS AI service..."
    
    # Create required directories
    mkdir -p .data/ai_models .data/model_cache
    
    # Copy example config if not exists
    if [ ! -f .env ]; then
        echo "📝 Creating .env configuration..."
        cp .env.ai.example .env
        echo "✅ Created .env file - you can customize AI settings there"
    fi
    
    echo "✅ Setup complete!"
    echo ""
    echo "🚀 Next steps:"
    echo "   1. Review configuration: cat .env"
    echo "   2. Start service: $0 start balanced"
    echo "   3. Check status: $0 status"
}

# Main command handling
case ${1:-help} in
    start)
        start_service $2
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service $2
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    models)
        list_models
        ;;
    switch)
        switch_tier $2
        ;;
    setup)
        setup_service
        ;;
    help|--help|-h|*)
        show_usage
        ;;
esac