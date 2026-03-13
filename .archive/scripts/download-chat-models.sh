#!/bin/bash

###############################################################################
# Replicatable Model Download Script
# Downloads only missing chat-capable LLM models to .data/ai_models/
# Checks availability before downloading
###############################################################################

MODELS_DIR=".data/ai_models"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure models directory exists
mkdir -p "$MODELS_DIR"

###############################################################################
# Model definitions (POSIX compatible)
###############################################################################

# Format: filename|url
MODELS_LIST="
zephyr-7b-beta.Q4_0.gguf|https://gpt4all.io/models/gguf/zephyr-7b-beta.Q4_0.gguf
openhermes-2-mistral-7B.Q4_0.gguf|https://gpt4all.io/models/gguf/openhermes-2-mistral-7B.Q4_0.gguf
mistral-7b-openorca.gguf|https://gpt4all.io/models/gguf/mistral-7b-openorca.gguf
neural-chat-7b-v3-1.Q4_0.gguf|https://gpt4all.io/models/gguf/neural-chat-7b-v3-1.Q4_0.gguf
WizardLM-7B-uncensored.Q4_K_M.gguf|https://huggingface.co/TheBloke/WizardLM-7B-uncensored-GGUF/resolve/main/WizardLM-7B-uncensored.Q4_K_M.gguf
tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf|https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
Airoboros-7B-GPT4-1.4.1.Q4_K_M.gguf|https://huggingface.co/TheBloke/Airoboros-7B-GPT4-1.4.1-GGUF/resolve/main/Airoboros-7B-GPT4-1.4.1.Q4_K_M.gguf
nous-hermes-2-mistral-7b-dpo.Q4_K_M.gguf|https://huggingface.co/TheBloke/Nous-Hermes-2-Mistral-7B-DPO-GGUF/resolve/main/nous-hermes-2-mistral-7b-dpo.Q4_K_M.gguf
starling-lm-7b-alpha.Q4_K_M.gguf|https://huggingface.co/TheBloke/Starling-LM-7B-alpha-GGUF/resolve/main/starling-lm-7b-alpha.Q4_K_M.gguf
"

###############################################################################
# Helper functions
###############################################################################

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

###############################################################################
# Main
###############################################################################

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       LLM Chat Models Download & Availability Checker          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check existing models
echo "📂 Checking: $MODELS_DIR"
echo ""

EXISTING_COUNT=0
MISSING_COUNT=0
TOTAL_EXISTING_SIZE=0

while IFS='|' read -r model url; do
  [ -z "$model" ] && continue
  
  if [ -f "$MODELS_DIR/$model" ]; then
    size=$(stat -f%z "$MODELS_DIR/$model" 2>/dev/null || stat -c%s "$MODELS_DIR/$model" 2>/dev/null)
    EXISTING_COUNT=$((EXISTING_COUNT + 1))
    TOTAL_EXISTING_SIZE=$((TOTAL_EXISTING_SIZE + size))
    echo "✅ $(format_size $size) - $model"
  else
    MISSING_COUNT=$((MISSING_COUNT + 1))
  fi
done <<< "$MODELS_LIST"

echo ""
if [ $EXISTING_COUNT -gt 0 ]; then
  echo "✅ Already have: $EXISTING_COUNT models ($(format_size $TOTAL_EXISTING_SIZE))"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "📥 AVAILABLE TO DOWNLOAD: $MISSING_COUNT models"
echo "════════════════════════════════════════════════════════════════"
echo ""

AVAILABLE_COUNT=0

while IFS='|' read -r model url; do
  [ -z "$model" ] && continue
  
  if [ ! -f "$MODELS_DIR/$model" ]; then
    printf "🔍 Checking: %-45s " "$model"
    
    if check_url_exists "$url"; then
      echo "✅ AVAILABLE"
      AVAILABLE_COUNT=$((AVAILABLE_COUNT + 1))
    else
      echo "❌ NOT FOUND"
    fi
  fi
done <<< "$MODELS_LIST"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

if [ $AVAILABLE_COUNT -eq 0 ]; then
  echo "ℹ️  No new models available to download"
  echo ""
  exit 0
fi

echo "🎯 SUMMARY:"
echo ""
echo "  Already downloaded:  $EXISTING_COUNT models ($(format_size $TOTAL_EXISTING_SIZE))"
echo "  Available to add:    $AVAILABLE_COUNT models"
echo "  Not accessible:      $((MISSING_COUNT - AVAILABLE_COUNT)) models"
echo ""

echo "📊 ESTIMATED MODEL SIZES:"
echo ""
cat << 'MODELS_INFO'
  Zephyr 7B              ~7.3 GB  (Better than base Mistral for chat)
  OpenHermes 2 Mistral   ~7.3 GB  (Excellent instruction following)
  Mistral 7B OpenOrca    ~7.3 GB  (Fine-tuned for QA)
  Neural Chat 7B v3.1    ~7.3 GB  (Intel optimized)
  WizardLM 7B Uncensored ~7.3 GB  (Strong reasoning)
  TinyLlama 1.1B Chat    ~1.1 GB  (Ultra-fast, lightweight)
  Airoboros 7B GPT4      ~7.3 GB  (Instruction-following)
  Nous Hermes 2 DPO      ~7.3 GB  (Advanced chat)
  Starling LM 7B Alpha   ~7.3 GB  (Optimized responses)
MODELS_INFO

echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "💾 Total space needed for all $AVAILABLE_COUNT models: ~60-70 GB"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo ""

# Check if --confirm flag is passed
if [ "$1" = "--confirm" ] || [ "$1" = "--download" ]; then
  echo "🚀 STARTING DOWNLOADS..."
  echo ""
  
  DOWNLOAD_COUNT=0
  while IFS='|' read -r model url; do
    [ -z "$model" ] && continue
    
    if [ ! -f "$MODELS_DIR/$model" ]; then
      DOWNLOAD_COUNT=$((DOWNLOAD_COUNT + 1))
      echo "[$DOWNLOAD_COUNT/$AVAILABLE_COUNT] ⬇️  $model"
      curl -L -o "$MODELS_DIR/$model" "$url"
      echo "✅ Downloaded"
      echo ""
    fi
  done <<< "$MODELS_LIST"
  
  echo "════════════════════════════════════════════════════════════════"
  echo "✅ Downloads complete!"
  echo ""
  ls -lh "$MODELS_DIR"/*.gguf 2>/dev/null | tail -n $DOWNLOAD_COUNT
  
else
  echo "To proceed with downloads, run:"
  echo ""
  echo "  ./download-chat-models.sh --confirm"
  echo ""
fi
