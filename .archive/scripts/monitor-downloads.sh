#!/bin/bash

# Trading OS Model Download Monitor
# Monitors GGUF and Transformers model downloads

set -e

cd "$(dirname "$0")/Backend/.data" || exit 1

echo "🤖 Trading OS AI Model Download Monitor"
echo "======================================"
echo ""

# Function to format size
format_size() {
    numfmt --to=iec-i --suffix=B "$1" 2>/dev/null || du -h <<< "$1" | cut -f1
}

# Check GGUF models (GPT4All)
echo "📦 GPT4All Models (.data/ai_models/)"
echo "---"

MISTRAL_FILE="ai_models/mistral-7b-instruct-v0.1.Q4_0.gguf"
NOUS_FILE="ai_models/nous-hermes-llama2-13b.q4_0.gguf"
ORCA_FILE="ai_models/orca-mini-3b-gguf2-q4_0.gguf"

if [ -f "$ORCA_FILE" ]; then
    orca_size=$(du -b "$ORCA_FILE" | cut -f1)
    orca_formatted=$(numfmt --to=iec-i --suffix=B "$orca_size" 2>/dev/null || echo "$(($orca_size / 1024 / 1024)) MB")
    echo "✅ Orca Mini: $orca_formatted / 1.9 GB"
else
    echo "❌ Orca Mini: Not found"
fi

if [ -f "$MISTRAL_FILE" ]; then
    mistral_size=$(du -b "$MISTRAL_FILE" | cut -f1)
    mistral_formatted=$(numfmt --to=iec-i --suffix=B "$mistral_size" 2>/dev/null || echo "$(($mistral_size / 1024 / 1024)) MB")
    mistral_pct=$((mistral_size * 100 / 4294967296))  # 4.1GB in bytes
    echo "⏳ Mistral: $mistral_formatted / 4.1 GB ($mistral_pct%)"
else
    echo "⏳ Mistral: Starting download..."
fi

if [ -f "$NOUS_FILE" ]; then
    nous_size=$(du -b "$NOUS_FILE" | cut -f1)
    nous_formatted=$(numfmt --to=iec-i --suffix=B "$nous_size" 2>/dev/null || echo "$(($nous_size / 1024 / 1024)) MB")
    nous_pct=$((nous_size * 100 / 7852548096))  # 7.3GB in bytes
    echo "⏳ Nous Hermes: $nous_formatted / 7.3 GB ($nous_pct%)"
else
    echo "⏳ Nous Hermes: Starting download..."
fi

echo ""
echo "🧠 HuggingFace Models (.data/model_cache/)"
echo "---"

# Check Transformers models
for model_name in "dolphin-2.6-mixtral-8x7b" "microsoft--phi-2" "codellama--CodeLlama-7b-Instruct-hf" "microsoft--DialoGPT-medium" "sentence-transformers--all-MiniLM-L6-v2" "ProsusAI--finbert"; do
    model_dir="model_cache/models--${model_name}"
    if [ -d "$model_dir" ]; then
        model_size=$(du -sb "$model_dir" | cut -f1)
        model_formatted=$(numfmt --to=iec-i --suffix=B "$model_size" 2>/dev/null || echo "$(($model_size / 1024 / 1024)) MB")
        
        if [[ "$model_name" == *"dolphin"* ]]; then
            model_pct=$((model_size * 100 / 27917287424))  # 26GB
            echo "⏳ Dolphin Mixtral: $model_formatted / 26 GB ($model_pct%)"
        elif [[ "$model_name" == *"phi-2"* ]]; then
            echo "✅ Phi-2: $model_formatted / 2.7 GB"
        elif [[ "$model_name" == *"CodeLlama"* ]]; then
            echo "✅ CodeLlama: $model_formatted / 13 GB"
        elif [[ "$model_name" == *"DialoGPT"* ]]; then
            echo "✅ DialoGPT: $model_formatted / 350 MB"
        elif [[ "$model_name" == *"MiniLM"* ]]; then
            echo "✅ MiniLM: $model_formatted / 87 MB"
        elif [[ "$model_name" == *"finbert"* ]]; then
            echo "✅ FinBERT: $model_formatted / 400 MB"
        fi
    fi
done

echo ""
echo "📊 Total Storage Usage"
echo "---"

if [ -d "ai_models" ]; then
    gguf_total=$(du -sb ai_models/ 2>/dev/null | cut -f1 || echo 0)
    gguf_formatted=$(numfmt --to=iec-i --suffix=B "$gguf_total" 2>/dev/null || echo "$(($gguf_total / 1024 / 1024)) MB")
    echo "GGUF Models: $gguf_formatted"
fi

if [ -d "model_cache" ]; then
    cache_total=$(du -sb model_cache/ 2>/dev/null | cut -f1 || echo 0)
    cache_formatted=$(numfmt --to=iec-i --suffix=B "$cache_total" 2>/dev/null || echo "$(($cache_total / 1024 / 1024)) MB")
    echo "Cached Models: $cache_formatted"
fi

# Check active downloads
echo ""
echo "🔄 Active Downloads"
echo "---"
download_count=$(pgrep -f "curl.*gguf" | wc -l)
echo "Active curl processes: $download_count"

if [ $download_count -gt 0 ]; then
    echo "✅ Downloads in progress..."
else
    echo "✅ No active downloads (check if complete)"
fi
