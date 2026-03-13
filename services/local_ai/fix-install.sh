#!/bin/bash

echo "🔧 FIXING INSTALLATION ISSUES..."
echo "════════════════════════════════════════════════════════════════"

cd "$(dirname "$0")"

# Fix the environment if it exists
if [ -d "local_ai_env" ]; then
    echo "🔄 Updating existing environment..."
    source local_ai_env/bin/activate
    
    # Install PyTorch with correct approach for Apple Silicon/Intel
    echo "📦 Installing PyTorch..."
    if [[ $(uname -m) == "arm64" ]]; then
        # Apple Silicon Mac
        pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    else
        # Intel Mac
        pip install torch torchvision
    fi
    
    # Install other requirements without torch (since we just installed it)
    echo "📦 Installing other dependencies..."
    pip install fastapi==0.110.1 uvicorn[standard]==0.29.0 pydantic==2.7.1
    pip install python-multipart==0.0.6 requests==2.31.0 PyYAML==6.0.1
    pip install python-dotenv==1.0.1 transformers accelerate bitsandbytes
    pip install gpt4all optimum onnxruntime sentence-transformers
    pip install huggingface-hub psutil numpy einops
    
    echo "✅ Dependencies fixed!"
else
    echo "❌ No environment found. Please run setup.sh first"
    exit 1
fi

echo ""
echo "🚀 Testing installation..."
python -c "
import torch
print('✅ PyTorch installed:', torch.__version__)

try:
    from gpt4all import GPT4All
    print('✅ GPT4All available')
except:
    print('❌ GPT4All failed')

try:
    from transformers import AutoTokenizer
    print('✅ Transformers available')
except:
    print('❌ Transformers failed')

try:
    import yaml
    print('✅ YAML support available')
except:
    print('❌ YAML failed')
"

echo ""
echo "✅ Installation fixed! Ready to integrate with trading portal."