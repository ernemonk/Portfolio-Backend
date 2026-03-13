#!/bin/bash

echo "🤖 Setting up Trading OS Local AI - OPTIMIZED EDITION"
echo "═══════════════════════════════════════════════════════"

# Performance tier selection
echo "📊 Select your performance tier:"
echo "1) Fast - Ultra-fast models for real-time trading (4GB)"
echo "2) Balanced - Best mix of speed & quality (8GB) [RECOMMENDED]"
echo "3) Quality - Highest intelligence models (15GB)"
echo "4) Full - All models for maximum capability (40GB+)"
echo ""
read -p "Choose tier (1-4) [default: 2]: " tier
tier=${tier:-2}

case $tier in
    1) PERF_TIER="fast" ;;
    2) PERF_TIER="balanced" ;;
    3) PERF_TIER="quality" ;;
    4) PERF_TIER="full" ;;
    *) PERF_TIER="balanced" ;;
esac

echo "🎯 Selected: $PERF_TIER tier"
echo ""

# Create optimized environment
echo "🏗️ Creating optimized Python environment..."
python3 -m venv local_ai_env --prompt="trading-ai"
source local_ai_env/bin/activate

# Set up performance environment variables
echo "⚡ Configuring performance optimizations..."
export HF_HOME="$HOME/.trading_os/model_cache"
export TRANSFORMERS_CACHE="$HOME/.trading_os/model_cache"
export HF_DATASETS_CACHE="$HOME/.trading_os/model_cache" 
export TORCH_HOME="$HOME/.trading_os/model_cache"
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4

# Create cache directories
mkdir -p "$HOME/.trading_os/ai_models"
mkdir -p "$HOME/.trading_os/model_cache"

echo "📦 Installing optimized dependencies..."
pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements.txt

echo "🧠 Pre-loading models for $PERF_TIER tier..."
python -c "
from model_config import ModelConfig
config = ModelConfig()
config.print_setup_guide('$PERF_TIER')
print('\n🚀 Starting model downloads...')

import sys
try:
    # Fast tier models
    if '$PERF_TIER' in ['fast', 'balanced', 'quality', 'full']:
        print('📥 Downloading Orca Mini 3B (fast)...')
        from gpt4all import GPT4All
        GPT4All('orca-mini-3b-gguf2-q4_0', model_path='$HOME/.trading_os/ai_models')
        
    # Balanced+ tier models  
    if '$PERF_TIER' in ['balanced', 'quality', 'full']:
        print('📥 Downloading Mistral 7B (balanced)...')
        GPT4All('mistral-7b-instruct-v0.1.Q4_0', model_path='$HOME/.trading_os/ai_models')
        
        print('📥 Downloading FinBERT (financial specialist)...')
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        AutoTokenizer.from_pretrained('ProsusAI/finbert', cache_dir='$HOME/.trading_os/model_cache')
        AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert', cache_dir='$HOME/.trading_os/model_cache')
        
    # Quality+ tier models
    if '$PERF_TIER' in ['quality', 'full']:
        print('📥 Downloading Nous Hermes 13B (quality)...')
        GPT4All('nous-hermes-llama2-13b.q4_0', model_path='$HOME/.trading_os/ai_models')
        
    # Embeddings (all tiers)
    print('📥 Downloading sentence embeddings...')
    from sentence_transformers import SentenceTransformer
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', cache_folder='$HOME/.trading_os/model_cache')
    
    print('✅ Model downloads complete!')
except Exception as e:
    print(f'⚠️  Some models may need manual download: {e}')
    print('You can download them later using the service API')
"

echo ""
echo "✅ Trading OS Local AI Setup Complete!"
echo "═══════════════════════════════════════════════════════"
echo "🎯 Performance Tier: $PERF_TIER"
echo "📁 Models Location: $HOME/.trading_os/ai_models"
echo "💾 Cache Location: $HOME/.trading_os/model_cache"
echo ""
echo "🚀 To start the service:"
echo "   cd $PWD"
echo "   source local_ai_env/bin/activate"
echo "   python src/main.py"
echo ""
echo "📡 Service endpoints:"
echo "   • Health: http://localhost:3008/health"
echo "   • Models: http://localhost:3008/v1/models" 
echo "   • Chat: http://localhost:3008/v1/chat/completions"
echo "   • Model Info: http://localhost:3008/models/info"
echo ""
echo "💡 Pro Tips:"
echo "   • Models auto-download on first use"
echo "   • Use 'fast' models for real-time trading"
echo "   • Use 'quality' models for analysis & research"
echo "   • Check /models/info for performance stats"
echo ""