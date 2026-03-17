#!/bin/bash

# ══════════════════════════════════════════════════════════════════════════
# Trading OS AI Management System
# Unified script for all AI operations: setup, management, models, monitoring
# ══════════════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="$SCRIPT_DIR/.data/ai_models"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

cd "$SCRIPT_DIR"

# ── Color Codes ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ── Helper Functions ───────────────────────────────────────────────────────

print_header() {
    echo -e "${CYAN}══════════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}║                    🤖 Trading OS AI Management                        ║${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════════════════════════════${NC}"
}

print_section() {
    echo ""
    echo -e "${BLUE}$1${NC}"
    echo "────────────────────────────────────────────────────────────────────────────"
}

format_size() {
    local bytes=$1
    if [ $bytes -lt 1024 ]; then
        echo "${bytes}B"
    elif [ $bytes -lt $((1024*1024)) ]; then
        echo "$((bytes / 1024))KB"
    elif [ $bytes -lt $((1024*1024*1024)) ]; then
        echo "$((bytes / 1024 / 1024))MB"
    else
        echo "$((bytes / 1024 / 1024 / 1024))GB"
    fi
}

check_url_exists() {
    local url=$1
    local response=$(curl -sI "$url" 2>/dev/null | head -1)
    if echo "$response" | grep -q "200\|302\|301"; then
        return 0
    else
        return 1
    fi
}

# ── Model Definitions ──────────────────────────────────────────────────────

FAST_MODELS="
tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf|https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
"

BALANCED_MODELS="
mistral-7b-instruct-v0.1.Q4_0.gguf|https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/mistral-7b-instruct-v0.1.Q4_0.gguf
zephyr-7b-beta.Q4_K_M.gguf|https://huggingface.co/TheBloke/zephyr-7B-beta-GGUF/resolve/main/zephyr-7b-beta.Q4_K_M.gguf
neural-chat-7b-v3-3.Q4_K_M.gguf|https://huggingface.co/TheBloke/neural-chat-7B-v3-3-GGUF/resolve/main/neural-chat-7b-v3-3.Q4_K_M.gguf
"

QUALITY_MODELS="
openhermes-2.5-mistral-7b.Q4_K_M.gguf|https://huggingface.co/TheBloke/OpenHermes-2.5-Mistral-7B-GGUF/resolve/main/openhermes-2.5-mistral-7b.Q4_K_M.gguf
nous-hermes-2-mistral-7b-dpo.Q4_K_M.gguf|https://huggingface.co/TheBloke/Nous-Hermes-2-Mistral-7B-DPO-GGUF/resolve/main/nous-hermes-2-mistral-7b-dpo.Q4_K_M.gguf
starling-lm-7b-alpha.Q4_K_M.gguf|https://huggingface.co/TheBloke/Starling-LM-7B-alpha-GGUF/resolve/main/starling-lm-7b-alpha.Q4_K_M.gguf
wizardlm-7b-v1.0.Q4_K_M.gguf|https://huggingface.co/TheBloke/WizardLM-7B-V1.0-GGUF/resolve/main/wizardlm-7b-v1.0.Q4_K_M.gguf
"

ALL_MODELS="$FAST_MODELS$BALANCED_MODELS$QUALITY_MODELS"

# ── Main Functions ─────────────────────────────────────────────────────────

show_menu() {
    clear
    print_header
    echo ""
    echo -e "${GREEN}🚀 Main Commands:${NC}"
    echo "  start [tier]     Start AI service (fast|balanced|quality)"
    echo "  stop             Stop AI service"  
    echo "  restart [tier]   Restart with new performance tier"
    echo "  status           Show service status and configuration"
    echo "  logs             Show real-time service logs"
    echo ""
    echo -e "${GREEN}🤖 Model Management:${NC}"
    echo "  models           List available and downloaded models"
    echo "  download [tier]  Download models for specific tier (fast|balanced|quality|all)"
    echo "  check            Check model availability and disk usage"
    echo "  cleanup          Clean unused models and cache"
    echo ""
    echo -e "${GREEN}⚙️  Configuration:${NC}"
    echo "  setup            Initial environment setup"
    echo "  switch <tier>    Switch performance tier"
    echo "  health           Run comprehensive health check"
    echo "  test             Test AI service endpoints"
    echo ""
    echo -e "${GREEN}📊 Monitoring:${NC}"
    echo "  monitor          Real-time monitoring dashboard"
    echo "  stats            Show usage statistics"
    echo ""
    echo -e "${BLUE}Performance Tiers:${NC}"
    echo -e "  ${YELLOW}fast${NC}       Ultra-fast models (~1-3GB) - Development/Testing"
    echo -e "  ${GREEN}balanced${NC}   Best mix (~7GB each) - Production [DEFAULT]"
    echo -e "  ${PURPLE}quality${NC}    Highest quality (~7GB each) - Research/Analysis"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  ./ai.sh start balanced    # Start with balanced tier"
    echo "  ./ai.sh download all      # Download all models"
    echo "  ./ai.sh monitor          # Real-time monitoring"
    echo ""
}

setup_environment() {
    print_section "🛠️  Setting up Trading OS AI Environment"
    
    # Create required directories
    mkdir -p .data/ai_models .data/model_cache
    echo -e "${GREEN}✅ Created model directories${NC}"
    
    # Copy example config if not exists
    if [ ! -f .env ]; then
        if [ -f .env.ai.example ]; then
            cp .env.ai.example .env
            echo -e "${GREEN}✅ Created .env configuration from template${NC}"
        else
            cat > .env << 'EOF'
# Trading OS AI Configuration
AI_PERFORMANCE_TIER=balanced
AI_MAX_MEMORY_GB=8
AI_PRELOAD_MODELS=true
AI_ENABLE_GPU=false
EOF
            echo -e "${GREEN}✅ Created default .env configuration${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  .env already exists - skipping${NC}"
    fi
    
    # Check Docker
    if ! docker --version >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker is available${NC}"
    
    # Check docker-compose
    if ! docker-compose --version >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker Compose not found. Please install Docker Compose.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker Compose is available${NC}"
    
    echo ""
    echo -e "${GREEN}✅ Setup complete!${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Review configuration: cat .env"
    echo "  2. Download models: ./ai.sh download balanced"
    echo "  3. Start service: ./ai.sh start"
}

start_service() {
    local tier=${1:-balanced}
    
    print_section "🚀 Starting Trading OS AI Service"
    echo -e "${BLUE}Performance Tier: ${tier}${NC}"
    
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
            echo -e "${RED}❌ Invalid tier: $tier. Use: fast, balanced, quality${NC}"
            exit 1
            ;;
    esac
    
    echo ""
    echo -e "${GREEN}✅ AI service started with '${tier}' tier${NC}"
    echo -e "${CYAN}📡 Service available at: http://localhost:3008${NC}"
    echo -e "${CYAN}🔍 Health check: curl http://localhost:3008/health${NC}"
    
    echo ""
    echo "⏳ Waiting for service to initialize..."
    sleep 3
    
    if curl -s http://localhost:3008/health &>/dev/null; then
        echo -e "${GREEN}✅ Service is responding to health checks${NC}"
    else
        echo -e "${YELLOW}⚠️  Service still starting up... Check logs with: ./ai.sh logs${NC}"
    fi
}

stop_service() {
    print_section "⏹️  Stopping Trading OS AI Service"
    docker-compose stop local_ai
    echo -e "${GREEN}✅ AI service stopped${NC}"
}

restart_service() {
    local tier=${1:-balanced}
    print_section "🔄 Restarting AI Service"
    echo -e "${BLUE}New Performance Tier: ${tier}${NC}"
    stop_service
    echo ""
    start_service $tier
}

show_status() {
    print_section "📊 Trading OS AI Status"
    
    if docker-compose ps local_ai | grep -q "Up"; then
        echo -e "${GREEN}✅ Service Status: Running${NC}"
        
        # Get current configuration
        local tier=$(docker-compose exec -T local_ai printenv AI_PERFORMANCE_TIER 2>/dev/null || echo "unknown")
        local memory=$(docker-compose exec -T local_ai printenv AI_MAX_MEMORY_GB 2>/dev/null || echo "unknown")
        local preload=$(docker-compose exec -T local_ai printenv AI_PRELOAD_MODELS 2>/dev/null || echo "unknown")
        
        echo -e "${BLUE}🎯 Performance Tier:${NC} $tier"
        echo -e "${BLUE}💾 Memory Limit:${NC} ${memory}GB"  
        echo -e "${BLUE}🔥 Preload Models:${NC} $preload"
        echo -e "${BLUE}📡 Endpoint:${NC} http://localhost:3008"
        
        # Try to get model info from API
        if curl -s http://localhost:3008/health &>/dev/null; then
            echo -e "${GREEN}🟢 Health Check: Passed${NC}"
        else
            echo -e "${YELLOW}🟡 Health Check: Service starting...${NC}"
        fi
        
        # Show resource usage
        local container_id=$(docker-compose ps -q local_ai)
        if [ -n "$container_id" ]; then
            local stats=$(docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemUsage}}" $container_id 2>/dev/null | tail -1)
            if [ -n "$stats" ]; then
                echo -e "${BLUE}📊 Resource Usage:${NC} $stats"
            fi
        fi
    else
        echo -e "${RED}❌ Service Status: Stopped${NC}"
    fi
    
    # Show model count
    if [ -d "$MODELS_DIR" ]; then
        local model_count=$(find "$MODELS_DIR" -name "*.gguf" 2>/dev/null | wc -l)
        local total_size=0
        if [ $model_count -gt 0 ]; then
            total_size=$(find "$MODELS_DIR" -name "*.gguf" -exec stat -f%z {} + 2>/dev/null | awk '{s+=$1} END {print s+0}')
        fi
        echo -e "${BLUE}🤖 Downloaded Models:${NC} $model_count ($(format_size $total_size))"
    fi
}

show_logs() {
    print_section "📋 Trading OS AI Logs"
    echo -e "${YELLOW}Press Ctrl+C to stop following logs${NC}"
    echo ""
    docker-compose logs -f local_ai
}

download_models() {
    local tier=${1:-balanced}
    
    print_section "📥 Downloading Models for '$tier' Tier"
    
    # Ensure models directory exists
    mkdir -p "$MODELS_DIR"
    
    local models_list=""
    case $tier in
        fast)
            models_list="$FAST_MODELS"
            echo -e "${YELLOW}⚡ Fast tier: Ultra-lightweight models for development${NC}"
            ;;
        balanced)
            models_list="$BALANCED_MODELS"
            echo -e "${GREEN}⚖️  Balanced tier: Best performance/quality mix${NC}"
            ;;
        quality)
            models_list="$QUALITY_MODELS"
            echo -e "${PURPLE}🧠 Quality tier: Highest quality models${NC}"
            ;;
        all)
            models_list="$ALL_MODELS"
            echo -e "${CYAN}🌟 All tiers: Complete model collection${NC}"
            ;;
        *)
            echo -e "${RED}❌ Invalid tier: $tier. Use: fast, balanced, quality, all${NC}"
            exit 1
            ;;
    esac
    
    echo ""
    
    # Count models to download
    local total_models=0
    local needed_models=0
    while IFS='|' read -r model url; do
        [ -z "$model" ] && continue
        total_models=$((total_models + 1))
        if [ ! -f "$MODELS_DIR/$model" ]; then
            needed_models=$((needed_models + 1))
        fi
    done <<< "$models_list"
    
    if [ $needed_models -eq 0 ]; then
        echo -e "${GREEN}✅ All models for '$tier' tier already downloaded${NC}"
        return
    fi
    
    echo -e "${BLUE}📊 Models to download: $needed_models / $total_models${NC}"
    echo ""
    
    # Download missing models
    local download_count=0
    while IFS='|' read -r model url; do
        [ -z "$model" ] && continue
        
        if [ ! -f "$MODELS_DIR/$model" ]; then
            download_count=$((download_count + 1))
            echo -e "${CYAN}[$download_count/$needed_models] ⬇️  Downloading: $model${NC}"
            
            if curl -L --progress-bar -o "$MODELS_DIR/$model" "$url"; then
                local size=$(stat -f%z "$MODELS_DIR/$model" 2>/dev/null || stat -c%s "$MODELS_DIR/$model" 2>/dev/null)
                echo -e "${GREEN}✅ Downloaded $(format_size $size)${NC}"
            else
                echo -e "${RED}❌ Failed to download $model${NC}"
                rm -f "$MODELS_DIR/$model"  # Clean up partial download
            fi
            echo ""
        fi
    done <<< "$models_list"
    
    echo -e "${GREEN}✅ Model downloads complete for '$tier' tier${NC}"
}

check_models() {
    print_section "🔍 Model Availability Check"
    
    echo -e "${BLUE}📂 Models directory: $MODELS_DIR${NC}"
    echo ""
    
    local existing_count=0
    local missing_count=0
    local total_size=0
    
    # Check existing models
    echo -e "${GREEN}✅ Downloaded Models:${NC}"
    while IFS='|' read -r model url; do
        [ -z "$model" ] && continue
        
        if [ -f "$MODELS_DIR/$model" ]; then
            local size=$(stat -f%z "$MODELS_DIR/$model" 2>/dev/null || stat -c%s "$MODELS_DIR/$model" 2>/dev/null)
            existing_count=$((existing_count + 1))
            total_size=$((total_size + size))
            echo "  ✅ $(format_size $size) - $model"
        fi
    done <<< "$ALL_MODELS"
    
    echo ""
    echo -e "${RED}❌ Missing Models:${NC}"
    while IFS='|' read -r model url; do
        [ -z "$model" ] && continue
        
        if [ ! -f "$MODELS_DIR/$model" ]; then
            missing_count=$((missing_count + 1))
            echo "  ❌ $model"
        fi
    done <<< "$ALL_MODELS"
    
    echo ""
    echo -e "${BLUE}📊 Summary:${NC}"
    echo "  Downloaded: $existing_count models ($(format_size $total_size))"
    echo "  Missing: $missing_count models"
    echo ""
    
    if [ $missing_count -gt 0 ]; then
        echo -e "${YELLOW}💡 To download missing models:${NC}"
        echo "  ./ai.sh download fast      # For development"
        echo "  ./ai.sh download balanced  # For production"  
        echo "  ./ai.sh download quality   # For research"
        echo "  ./ai.sh download all       # Everything"
    fi
}

run_health_check() {
    print_section "🏥 Comprehensive Health Check"
    
    # Check Docker
    if docker --version >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Docker: Available${NC}"
    else
        echo -e "${RED}❌ Docker: Not found${NC}"
    fi
    
    # Check Docker Compose
    if docker-compose --version >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Docker Compose: Available${NC}"
    else
        echo -e "${RED}❌ Docker Compose: Not found${NC}"
    fi
    
    # Check service
    if docker-compose ps local_ai | grep -q "Up"; then
        echo -e "${GREEN}✅ AI Service: Running${NC}"
        
        # Test health endpoint
        if curl -s http://localhost:3008/health &>/dev/null; then
            echo -e "${GREEN}✅ Health Endpoint: Responding${NC}"
        else
            echo -e "${YELLOW}⚠️  Health Endpoint: Not responding${NC}"
        fi
        
        # Test models endpoint
        if curl -s http://localhost:3008/models/info &>/dev/null; then
            echo -e "${GREEN}✅ Models Endpoint: Responding${NC}"
        else
            echo -e "${YELLOW}⚠️  Models Endpoint: Not responding${NC}"
        fi
    else
        echo -e "${RED}❌ AI Service: Stopped${NC}"
    fi
    
    # Check disk space
    local available=$(df "$MODELS_DIR" 2>/dev/null | tail -1 | awk '{print $4*1024}' || echo "0")
    if [ $available -gt 0 ]; then
        echo -e "${GREEN}✅ Disk Space: $(format_size $available) available${NC}"
        if [ $available -lt $((10*1024*1024*1024)) ]; then  # Less than 10GB
            echo -e "${YELLOW}⚠️  Low disk space - consider cleanup${NC}"
        fi
    fi
    
    # Check configuration
    if [ -f ".env" ]; then
        echo -e "${GREEN}✅ Configuration: Found .env file${NC}"
    else
        echo -e "${YELLOW}⚠️  Configuration: No .env file${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}🎯 System Status: Ready for AI operations${NC}"
}

show_monitor() {
    print_section "📊 Real-time AI Monitoring"
    echo -e "${YELLOW}Press Ctrl+C to exit monitoring${NC}"
    echo ""
    
    while true; do
        clear
        print_header
        show_status
        
        if docker-compose ps local_ai | grep -q "Up"; then
            echo ""
            echo -e "${BLUE}📈 Real-time Stats:${NC}"
            local container_id=$(docker-compose ps -q local_ai)
            if [ -n "$container_id" ]; then
                docker stats --no-stream $container_id 2>/dev/null || echo "Stats unavailable"
            fi
        fi
        
        echo ""
        echo -e "${CYAN}Last updated: $(date)${NC}"
        sleep 5
    done
}

cleanup_models() {
    print_section "🧹 Cleaning Up Models and Cache"
    
    echo -e "${YELLOW}⚠️  This will remove all downloaded models and cache${NC}"
    read -p "Continue? [y/N]: " confirm
    
    if [[ $confirm =~ ^[Yy]$ ]]; then
        # Stop service first
        if docker-compose ps local_ai | grep -q "Up"; then
            echo "Stopping AI service..."
            stop_service
        fi
        
        # Clean models
        if [ -d "$MODELS_DIR" ]; then
            rm -rf "$MODELS_DIR"/*.gguf 2>/dev/null || true
            echo -e "${GREEN}✅ Removed downloaded models${NC}"
        fi
        
        # Clean cache
        if [ -d ".data/model_cache" ]; then
            rm -rf .data/model_cache/* 2>/dev/null || true
            echo -e "${GREEN}✅ Cleared model cache${NC}"
        fi
        
        # Clean Docker images
        docker-compose down local_ai 2>/dev/null || true
        echo -e "${GREEN}✅ Stopped containers${NC}"
        
        echo ""
        echo -e "${GREEN}✅ Cleanup complete${NC}"
        echo -e "${CYAN}💡 To reinstall: ./ai.sh setup && ./ai.sh download balanced${NC}"
    else
        echo -e "${YELLOW}❌ Cleanup cancelled${NC}"
    fi
}

test_endpoints() {
    print_section "🧪 Testing AI Service Endpoints"
    
    if ! curl -s http://localhost:3008/health &>/dev/null; then
        echo -e "${RED}❌ Service not running. Start with: ./ai.sh start${NC}"
        return 1
    fi
    
    echo "Testing health endpoint..."
    if curl -s http://localhost:3008/health | grep -q "ok\|healthy\|status"; then
        echo -e "${GREEN}✅ Health endpoint working${NC}"
    else
        echo -e "${RED}❌ Health endpoint failed${NC}"
    fi
    
    echo ""
    echo "Testing models endpoint..."
    if curl -s http://localhost:3008/models/info &>/dev/null; then
        echo -e "${GREEN}✅ Models endpoint working${NC}"
        echo -e "${CYAN}📊 Available models:${NC}"
        curl -s http://localhost:3008/models/info | head -10
    else
        echo -e "${YELLOW}⚠️  Models endpoint not responding${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}✅ Endpoint tests complete${NC}"
}

# ── Main Command Handling ──────────────────────────────────────────────────

case ${1:-menu} in
    # Core service commands
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
    switch)
        if [ -z "$2" ]; then
            echo -e "${RED}❌ Please specify tier: fast, balanced, quality${NC}"
            exit 1
        fi
        restart_service $2
        ;;
        
    # Model management
    models)
        check_models
        ;;
    download)
        download_models $2
        ;;
    check)
        check_models
        ;;
    cleanup)
        cleanup_models
        ;;
        
    # Configuration and health
    setup)
        setup_environment
        ;;
    health)
        run_health_check
        ;;
    test)
        test_endpoints
        ;;
        
    # Monitoring
    monitor)
        show_monitor
        ;;
    stats)
        show_status
        ;;
        
    # Help and menu
    menu)
        show_menu
        ;;
    help|--help|-h)
        show_menu
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $1${NC}"
        echo ""
        show_menu
        exit 1
        ;;
esac