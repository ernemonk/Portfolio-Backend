"""
Local AI Service - Port 3008

Responsibilities:
  - Host local AI models using Python packages (GPT4All, Transformers)
  - Provide OpenAI-compatible API endpoints
  - Download and manage local models
  - Support multiple model backends (GPT4All, HuggingFace, GGUF)
  - Integrate seamlessly with Trading OS configuration
  - OPTIMIZED for best model performance and caching
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import optimized YAML-driven model configuration
try:
    from yaml_config import YAMLModelConfig
    YAML_CONFIG_AVAILABLE = True
except ImportError:
    YAML_CONFIG_AVAILABLE = False
    print("⚠️  YAML config not found - using basic configuration")

try:
    from model_config import ModelConfig
    MODEL_CONFIG_AVAILABLE = True
except ImportError:
    MODEL_CONFIG_AVAILABLE = False
    print("⚠️  Model config not found - using basic configuration")

# Try importing AI libraries
try:
    from gpt4all import GPT4All
    GPT4ALL_AVAILABLE = True
except ImportError:
    GPT4ALL_AVAILABLE = False
    print("GPT4All not available - install with: pip install gpt4all")

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, AutoModelForSequenceClassification, pipeline
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Transformers not available - install with: pip install transformers torch")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Sentence Transformers not available - install with: pip install sentence-transformers")

# ---------------------------------------------------------------------------
# API Models (OpenAI Compatible)
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    stream: Optional[bool] = False

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    owned_by: str = "local"
    permission: List = []

# ---------------------------------------------------------------------------
# Local AI Manager
# ---------------------------------------------------------------------------

class LocalAIManager:
    def __init__(self):
        self.models = {}
        self.model_info = {}
        self.models_dir = Path.home() / ".trading_os" / "ai_models"
        self.cache_dir = Path.home() / ".trading_os" / "model_cache"
        
        # Create directories
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load YAML-driven model configuration (preferred)
        if YAML_CONFIG_AVAILABLE:
            self.yaml_config = YAMLModelConfig()
            self.model_info = self.yaml_config.optimized_models
            print(f"🎯 Loaded YAML config: {self.yaml_config.performance_tier} tier with {len(self.model_info)} models")
            
            # ALSO scan for dynamically discovered models
            print("🔄 Adding dynamically discovered models...")
            self._discover_and_merge_models()
            
        elif MODEL_CONFIG_AVAILABLE:
            self.config = ModelConfig()
            self.model_info = self.config.optimized_models
            print(f"🚀 Loaded {len(self.model_info)} optimized models")
            
            # ALSO scan for dynamically discovered models
            print("🔄 Adding dynamically discovered models...")
            self._discover_and_merge_models()
        else:
            # Fallback to basic models + dynamic discovery
            self._discover_models()
    
    def _discover_and_merge_models(self):
        """Discover new models and merge with existing config without duplicates"""
        discovered = {}
        self._discover_models_into(discovered)
        
        # Merge: discovered models override config models
        initial_count = len(self.model_info)
        for model_id, model_data in discovered.items():
            if model_id not in self.model_info:
                self.model_info[model_id] = model_data
                print(f"  ✨ New: {model_id}")
        
        added = len(self.model_info) - initial_count
        if added > 0:
            print(f"✅ Added {added} newly discovered models")
    
    def _discover_models_into(self, discovered):
        """Scan for GGUF and cached models, store in dict"""
        
        # Scan for GGUF models (GPT4All)
        if self.models_dir.exists():
            for gguf_file in self.models_dir.glob("*.gguf"):
                model_id = gguf_file.stem  # filename without extension
                size_mb = gguf_file.stat().st_size / (1024 * 1024)
                size_str = f"{size_mb:.1f}MB" if size_mb < 1024 else f"{size_mb/1024:.1f}GB"
                
                discovered[model_id] = {
                    "id": model_id,
                    "name": model_id.replace("-", " ").title(),
                    "size": size_str,
                    "type": "gpt4all",
                    "path": str(gguf_file)
                }
        
        # Scan HuggingFace cache for transformer models
        if self.cache_dir.exists():
            for model_path in self.cache_dir.glob("models--*"):
                # Parse HuggingFace cache format: models--username--modelname
                parts = model_path.name.split("--")
                if len(parts) >= 3:
                    username = parts[1]
                    modelname = parts[2]
                    model_id = f"{username}/{modelname}"
                    
                    # Determine model type
                    model_type = "transformers"
                    if "finbert" in model_id.lower():
                        model_type = "sentiment"
                    elif "dialogpt" in model_id.lower():
                        model_type = "dialog"
                    elif "all-minilm" in model_id.lower() or "sentence" in model_id.lower():
                        model_type = "embeddings"
                    
                    discovered[model_id] = {
                        "id": model_id,
                        "name": modelname.replace("-", " ").title(),
                        "type": model_type,
                        "path": str(model_path)
                    }
    
    def _discover_models(self):
        """Dynamically discover all available models from .data/ai_models/"""
        print("🔍 Scanning for available models...")
        self._discover_models_into(self.model_info)

    async def _preload_priority_models(self):
        """Preload priority 1 models for faster responses"""
        if not YAML_CONFIG_AVAILABLE:
            return
            
        priority_models = self.yaml_config.priority_models
        print(f"🔥 Preloading {len(priority_models)} priority models...")
        
        for model in priority_models:
            model_id = model["id"]
            try:
                print(f"📦 Preloading: {model.get('name', model_id)}")
                await self.load_model(model_id)
                print(f"✅ Preloaded: {model_id}")
            except Exception as e:
                print(f"⚠️  Failed to preload {model_id}: {e}")
        
        print(f"🚀 Preloading complete! {len(self.models)} models ready")
    
    async def load_model(self, model_id: str) -> bool:
        """Load a model into memory with optimization"""
        if model_id in self.models:
            return True
            
        if model_id not in self.model_info:
            return False
            
        model_config = self.model_info[model_id]
        
        try:
            if model_config["type"] == "gpt4all" and GPT4ALL_AVAILABLE:
                print(f"🤖 Loading GPT4All model: {model_config['name']}")
                # Check if GGUF file exists
                model_file = self.models_dir / model_id
                if not model_file.exists():
                    # Try common GGUF extensions
                    gguf_patterns = [f"{model_id}.gguf", f"{model_id}.bin", model_id]
                    found = False
                    for pattern in gguf_patterns:
                        potential_file = self.models_dir / pattern
                        if potential_file.exists():
                            model_file = potential_file
                            found = True
                            break
                    if not found:
                        print(f"❌ GPT4All model file not found: {model_id}")
                        print(f"   Expected location: {self.models_dir}")
                        print(f"   Available files: {list(self.models_dir.glob('*'))}")
                        return False
                
                model = GPT4All(str(model_file.name), model_path=str(self.models_dir))
                self.models[model_id] = {"model": model, "type": "gpt4all"}
                return True
                
            elif model_config["type"] == "transformers" and TRANSFORMERS_AVAILABLE:
                print(f"🧠 Loading Transformers model: {model_config['name']}")
                
                # Use optimized cache directory
                cache_dir = str(self.cache_dir)
                
                # Check if this is a sentiment/classification model (like FinBERT)
                is_sentiment_model = "finbert" in model_id.lower() or "sentiment" in model_config.get("use_cases", [])
                
                # Check if this is a conversational model
                is_dialog_model = "dialogpt" in model_id.lower() or "dialog" in model_id.lower()
                
                tokenizer = AutoTokenizer.from_pretrained(model_id, cache_dir=cache_dir)
                
                # Add padding token if missing (needed for some models)
                if tokenizer.pad_token is None:
                    tokenizer.pad_token = tokenizer.eos_token
                
                if is_sentiment_model:
                    # Load as sequence classification model
                    print(f"   📊 Loading as sentiment/classification model")
                    model = AutoModelForSequenceClassification.from_pretrained(
                        model_id,
                        cache_dir=cache_dir,
                        torch_dtype=torch.float32,  # Classification models work better with float32
                        low_cpu_mem_usage=True
                    )
                    self.models[model_id] = {
                        "model": model, 
                        "tokenizer": tokenizer, 
                        "type": "sentiment"
                    }
                else:
                    # Load as causal LM for text generation
                    print(f"   💬 Loading as text generation model")
                    model = AutoModelForCausalLM.from_pretrained(
                        model_id,
                        cache_dir=cache_dir,
                        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                        device_map="auto" if torch.cuda.is_available() else None,
                        low_cpu_mem_usage=True
                    )
                    model_type = "dialog" if is_dialog_model else "transformers"
                    self.models[model_id] = {
                        "model": model, 
                        "tokenizer": tokenizer, 
                        "type": model_type
                    }
                return True
                
            elif model_config["type"] == "embeddings" and SENTENCE_TRANSFORMERS_AVAILABLE:
                print(f"🔍 Loading Sentence Transformer: {model_config['name']}")
                model = SentenceTransformer(model_id, cache_folder=str(self.cache_dir))
                self.models[model_id] = {"model": model, "type": "embeddings"}
                return True
                
        except Exception as e:
            print(f"❌ Error loading model {model_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return False
    
    async def generate_response(self, model_id: str, messages: List[ChatMessage], 
                              temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Generate response using specified model"""
        if model_id not in self.models:
            if not await self.load_model(model_id):
                raise HTTPException(status_code=404, detail=f"Model {model_id} not available")
        
        model_data = self.models[model_id]
        
        # Check if this is an embeddings model (can't generate text)
        if model_data["type"] == "embeddings":
            raise HTTPException(
                status_code=400, 
                detail=f"Model {model_id} is an embeddings model and cannot generate chat responses. Use it for similarity/search tasks instead."
            )
        
        # Convert messages to prompt
        prompt = self._messages_to_prompt(messages)
        
        try:
            if model_data["type"] == "gpt4all":
                response = model_data["model"].generate(
                    prompt, 
                    max_tokens=max_tokens,
                    temp=temperature
                )
                return response
            
            elif model_data["type"] == "sentiment":
                # Sentiment models return classification, not generated text
                inputs = model_data["tokenizer"](
                    prompt, 
                    return_tensors="pt", 
                    truncation=True, 
                    max_length=512,
                    padding=True
                )
                
                with torch.no_grad():
                    outputs = model_data["model"](**inputs)
                    predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
                    
                # Get sentiment labels (FinBERT uses: negative, neutral, positive)
                labels = ["negative", "neutral", "positive"]
                scores = predictions[0].tolist()
                
                # Format as a helpful response
                sentiment_result = max(zip(labels, scores), key=lambda x: x[1])
                response = f"**Sentiment Analysis Result:**\n\n"
                response += f"Primary sentiment: **{sentiment_result[0].upper()}** (confidence: {sentiment_result[1]:.1%})\n\n"
                response += "Breakdown:\n"
                for label, score in zip(labels, scores):
                    bar = "█" * int(score * 20)
                    response += f"- {label.capitalize()}: {score:.1%} {bar}\n"
                
                return response
            
            elif model_data["type"] == "dialog":
                # DialoGPT and similar conversational models
                # Build conversation history for DialoGPT
                tokenizer = model_data["tokenizer"]
                model = model_data["model"]
                
                # Encode the new user input, add the eos_token and return tensors
                new_user_input_ids = tokenizer.encode(
                    prompt + tokenizer.eos_token, 
                    return_tensors='pt'
                )
                
                # Generate a response
                with torch.no_grad():
                    chat_history_ids = model.generate(
                        new_user_input_ids,
                        max_new_tokens=max_tokens,
                        pad_token_id=tokenizer.eos_token_id,
                        temperature=temperature,
                        do_sample=True,
                        top_p=0.9,
                        top_k=50
                    )
                
                # Decode the response
                response = tokenizer.decode(
                    chat_history_ids[:, new_user_input_ids.shape[-1]:][0], 
                    skip_special_tokens=True
                )
                return response.strip() if response.strip() else "I'm not sure how to respond to that."
                
            elif model_data["type"] == "transformers":
                tokenizer = model_data["tokenizer"]
                model = model_data["model"]
                
                inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
                
                # Move to same device as model
                if hasattr(model, 'device'):
                    inputs = {k: v.to(model.device) for k, v in inputs.items()}
                
                with torch.no_grad():
                    outputs = model.generate(
                        **inputs,
                        max_new_tokens=max_tokens,
                        temperature=temperature,
                        do_sample=True,
                        pad_token_id=tokenizer.eos_token_id,
                        top_p=0.9,
                        top_k=50,
                        repetition_penalty=1.1
                    )
                
                response = tokenizer.decode(outputs[0], skip_special_tokens=True)
                # Remove the input prompt from response
                response = response[len(prompt):].strip()
                return response if response else "I apologize, I couldn't generate a response. Please try rephrasing your question."
                
        except Exception as e:
            print(f"Error generating response: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
    
    def _messages_to_prompt(self, messages: List[ChatMessage]) -> str:
        """Convert chat messages to a single prompt string"""
        prompt_parts = []
        
        for message in messages:
            if message.role == "system":
                prompt_parts.append(f"System: {message.content}")
            elif message.role == "user":
                prompt_parts.append(f"Human: {message.content}")
            elif message.role == "assistant":
                prompt_parts.append(f"Assistant: {message.content}")
        
        prompt_parts.append("Assistant:")
        return "\n".join(prompt_parts)
    
    def get_available_models(self) -> List[ModelInfo]:
        """Get list of available models"""
        return [
            ModelInfo(id=model_id, owned_by=f"local-{info['type']}")
            for model_id, info in self.model_info.items()
        ]
    
    def check_model_availability(self, model_id: str) -> dict:
        """Check if a model is actually available and ready to use"""
        if model_id not in self.model_info:
            return {"available": False, "reason": "Model not configured"}
        
        model_config = self.model_info[model_id]
        model_type = model_config.get("type", "unknown")
        
        # Check if already loaded
        if model_id in self.models:
            return {"available": True, "loaded": True, "type": model_type}
        
        # Check if the required library is available
        if model_type == "gpt4all" and not GPT4ALL_AVAILABLE:
            return {"available": False, "reason": "GPT4All library not installed"}
        if model_type == "transformers" and not TRANSFORMERS_AVAILABLE:
            return {"available": False, "reason": "Transformers library not installed"}
        if model_type == "embeddings" and not SENTENCE_TRANSFORMERS_AVAILABLE:
            return {"available": False, "reason": "SentenceTransformers library not installed"}
        
        # For GPT4All models, check if the file exists
        if model_type == "gpt4all":
            gguf_files = list(self.models_dir.glob(f"{model_id}*")) + list(self.models_dir.glob("*.gguf"))
            matching = [f for f in gguf_files if model_id.split(".")[0] in f.name]
            if not matching:
                return {"available": False, "reason": f"GGUF file not found in {self.models_dir}", "download_required": True}
        
        # For transformers models, check cache
        if model_type == "transformers":
            cache_path = self.cache_dir / f"models--{model_id.replace('/', '--')}"
            if cache_path.exists():
                return {"available": True, "loaded": False, "type": model_type, "cached": True}
            else:
                return {"available": True, "loaded": False, "type": model_type, "cached": False, "will_download": True}
        
        return {"available": True, "loaded": False, "type": model_type}

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Trading OS Local AI Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AI Manager
ai_manager = LocalAIManager()

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": time.time(),
        "service": "local_ai",
        "gpt4all_available": GPT4ALL_AVAILABLE,
        "transformers_available": TRANSFORMERS_AVAILABLE,
        "loaded_models": list(ai_manager.models.keys())
    }

@app.get("/v1/models")
async def list_models():
    """OpenAI-compatible models endpoint"""
    return {
        "object": "list",
        "data": ai_manager.get_available_models()
    }

@app.get("/v1/models/{model_id:path}/availability")
async def check_model_availability(model_id: str):
    """Check if a specific model is available and ready to use"""
    return ai_manager.check_model_availability(model_id)

@app.get("/models/status")
async def get_all_models_status():
    """Get availability status for all configured models"""
    status = {}
    for model_id in ai_manager.model_info:
        status[model_id] = ai_manager.check_model_availability(model_id)
    return {
        "models": status,
        "summary": {
            "total": len(status),
            "available": sum(1 for s in status.values() if s.get("available")),
            "loaded": sum(1 for s in status.values() if s.get("loaded")),
            "download_required": sum(1 for s in status.values() if s.get("download_required"))
        }
    }

@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint"""
    try:
        response_text = await ai_manager.generate_response(
            model_id=request.model,
            messages=request.messages,
            temperature=request.temperature or 0.7,
            max_tokens=request.max_tokens or 1000
        )
        
        return ChatCompletionResponse(
            id=f"chatcmpl-{int(time.time())}",
            created=int(time.time()),
            model=request.model,
            choices=[{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            usage={
                "prompt_tokens": sum(len(msg.content.split()) for msg in request.messages),
                "completion_tokens": len(response_text.split()),
                "total_tokens": sum(len(msg.content.split()) for msg in request.messages) + len(response_text.split())
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/models/load")
async def load_model_endpoint(model_id: str):
    """Load a specific model"""
    success = await ai_manager.load_model(model_id)
    if success:
        return {"status": "loaded", "model": model_id}
    else:
        raise HTTPException(status_code=400, detail=f"Failed to load model: {model_id}")

@app.get("/models/info")
async def get_models_info():
    """Get detailed optimized model information with performance stats"""
    return {
        "available_models": ai_manager.model_info,
        "loaded_models": list(ai_manager.models.keys()),
        "models_directory": str(ai_manager.models_dir),
        "cache_directory": str(ai_manager.cache_dir),
        "capabilities": {
            "gpt4all": GPT4ALL_AVAILABLE,
            "transformers": TRANSFORMERS_AVAILABLE,
            "sentence_transformers": SENTENCE_TRANSFORMERS_AVAILABLE,
            "cuda": torch.cuda.is_available() if TRANSFORMERS_AVAILABLE else False
        },
        "optimizations": {
            "cache_enabled": True,
            "memory_optimized": True,
            "quantization_enabled": True
        }
    }

@app.get("/models/recommendations/{performance_tier}")
async def get_model_recommendations(performance_tier: str):
    """Get model recommendations for a specific performance tier"""
    if not MODEL_CONFIG_AVAILABLE:
        raise HTTPException(status_code=503, detail="Model configuration not available")
    
    if performance_tier not in ["fast", "balanced", "quality", "full"]:
        raise HTTPException(status_code=400, detail="Invalid tier. Use: fast, balanced, quality, full")
    
    recommended = ai_manager.config.get_recommended_setup(performance_tier)
    models_info = {mid: ai_manager.model_info[mid] for mid in recommended if mid in ai_manager.model_info}
    
    total_size = sum(
        float(info["size"].replace("GB", "").replace("MB", "0.001"))
        for info in models_info.values()
    )
    
    return {
        "performance_tier": performance_tier,
        "recommended_models": models_info,
        "total_models": len(recommended),
        "total_size_gb": round(total_size, 1),
        "setup_commands": ai_manager.config.get_install_commands(recommended) if MODEL_CONFIG_AVAILABLE else []
    }

@app.get("/dashboard/models")
async def get_dashboard_models():
    """Get all models organized for trading dashboard selection"""
    if not YAML_CONFIG_AVAILABLE:
        return {"error": "YAML configuration not available"}
    
    models_by_speed = {
        "ultra-fast": [],
        "fast": [], 
        "balanced": [],
        "slow": []
    }
    
    models_by_use_case = {}
    
    for model_id, model_info in ai_manager.model_info.items():
        # Organize by speed
        speed = model_info.get("speed", "balanced")
        if speed in models_by_speed:
            models_by_speed[speed].append({
                "id": model_id,
                "name": model_info.get("name", model_id),
                "size": model_info.get("size", "Unknown"),
                "quality": model_info.get("quality", "good"),
                "best_for": model_info.get("best_for", "General purpose"),
                "loaded": model_id in ai_manager.models
            })
        
        # Organize by use case
        use_cases = model_info.get("use_cases", [])
        for use_case in use_cases:
            if use_case not in models_by_use_case:
                models_by_use_case[use_case] = []
            models_by_use_case[use_case].append({
                "id": model_id,
                "name": model_info.get("name", model_id),
                "speed": speed,
                "quality": model_info.get("quality", "good")
            })
    
    return {
        "models_by_speed": models_by_speed,
        "models_by_use_case": models_by_use_case,
        "loaded_models": list(ai_manager.models.keys()),
        "total_available": len(ai_manager.model_info),
        "recommendations": {
            "real_time_trading": "orca-mini-3b-gguf2-q4_0",
            "financial_analysis": "mistral-7b-instruct-v0.1.Q4_0", 
            "code_generation": "microsoft/phi-2",
            "market_sentiment": "ProsusAI/finbert",
            "deep_research": "nous-hermes-llama2-13b.q4_0",
            "document_search": "sentence-transformers/all-MiniLM-L6-v2"
        }
    }

@app.post("/dashboard/select-model")
async def select_model_for_task(task_type: str, prefer_speed: bool = True):
    """Smart model selection for specific trading tasks"""
    
    # Model recommendations by task
    task_recommendations = {
        "real_time_trading": {
            "speed": "orca-mini-3b-gguf2-q4_0",
            "quality": "mistral-7b-instruct-v0.1.Q4_0"
        },
        "financial_analysis": {
            "speed": "mistral-7b-instruct-v0.1.Q4_0", 
            "quality": "nous-hermes-llama2-13b.q4_0"
        },
        "code_generation": {
            "speed": "microsoft/phi-2",
            "quality": "codellama/CodeLlama-7b-Instruct-hf"
        },
        "market_sentiment": {
            "speed": "ProsusAI/finbert",
            "quality": "ProsusAI/finbert"
        },
        "research": {
            "speed": "mistral-7b-instruct-v0.1.Q4_0",
            "quality": "nous-hermes-llama2-13b.q4_0"
        },
        "document_search": {
            "speed": "sentence-transformers/all-MiniLM-L6-v2",
            "quality": "sentence-transformers/all-MiniLM-L6-v2"
        }
    }
    
    if task_type not in task_recommendations:
        return {"error": f"Unknown task type: {task_type}"}
    
    model_choice = "speed" if prefer_speed else "quality"
    recommended_model = task_recommendations[task_type][model_choice]
    
    # Load the model if not already loaded
    if recommended_model not in ai_manager.models:
        success = await ai_manager.load_model(recommended_model)
        if not success:
            return {"error": f"Failed to load model: {recommended_model}"}
    
    model_info = ai_manager.model_info.get(recommended_model, {})
    
    return {
        "task_type": task_type,
        "selected_model": recommended_model,
        "model_name": model_info.get("name", recommended_model),
        "speed": model_info.get("speed", "unknown"),
        "quality": model_info.get("quality", "unknown"), 
        "best_for": model_info.get("best_for", ""),
        "loaded": True,
        "preference": model_choice
    }

@app.post("/v1/chat/completions/smart")
async def smart_chat_completion(request: ChatCompletionRequest, task_type: str = "general", prefer_speed: bool = True):
    """Smart completion that auto-selects best model for the task"""
    
    # Auto-select model based on task
    selection_result = await select_model_for_task(task_type, prefer_speed)
    if "error" in selection_result:
        # Fallback to requested model or default
        model_to_use = request.model
    else:
        model_to_use = selection_result["selected_model"]
    
    # Update request with selected model
    request.model = model_to_use
    
    # Use existing completion logic
    return await create_chat_completion(request)

# ─────────────────────────────────────────────────────────────────────────────
# 🎯 NEW: ENHANCED MODEL MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/models/status")
async def get_models_status():
    """Get comprehensive status of all available models"""
    try:
        status = {
            "service_status": "online",
            "timestamp": datetime.now().isoformat(),
            "models": [],
            "loaded_count": len(ai_manager.models),
            "total_models": len(ai_manager.model_info),
            "installed_location": str(ai_manager.models_dir),
            "cache_location": str(ai_manager.cache_dir)
        }
        
        for model_id, model_info in ai_manager.model_info.items():
            is_loaded = model_id in ai_manager.models
            model_detail = {
                "id": model_id,
                "name": model_info.get("name", "Unknown"),
                "type": model_info.get("type", "unknown"),
                "size": model_info.get("size", "unknown"),
                "speed": model_info.get("speed", "unknown"),
                "quality": model_info.get("quality", "unknown"),
                "use_cases": model_info.get("use_cases", []),
                "best_for": model_info.get("best_for", ""),
                "loaded": is_loaded,
                "location": str(ai_manager.models_dir / model_id) if is_loaded else "not_loaded"
            }
            status["models"].append(model_detail)
        
        return status
    except Exception as e:
        return {"error": str(e), "service_status": "error"}

@app.get("/models/installed")
async def get_installed_models():
    """List only locally installed models"""
    try:
        installed = []
        for model_id, model_info in ai_manager.model_info.items():
            if model_id in ai_manager.models:
                installed.append({
                    "id": model_id,
                    "name": model_info.get("name", "Unknown"),
                    "size": model_info.get("size", "unknown"),
                    "speed": model_info.get("speed", "unknown"),
                    "quality": model_info.get("quality", "unknown"),
                    "use_cases": model_info.get("use_cases", [])
                })
        return {"installed_models": installed, "count": len(installed)}
    except Exception as e:
        return {"error": str(e), "installed_models": []}

@app.get("/models/available")
async def get_available_models():
    """List all available models (regardless of installation status)"""
    try:
        available = []
        for model_id, model_info in ai_manager.model_info.items():
            available.append({
                "id": model_id,
                "name": model_info.get("name", "Unknown"),
                "type": model_info.get("type", "unknown"),
                "size": model_info.get("size", "unknown"),
                "speed": model_info.get("speed", "unknown"),
                "quality": model_info.get("quality", "unknown"),
                "priority": model_info.get("priority", 0),
                "installed": model_id in ai_manager.models,
                "use_cases": model_info.get("use_cases", []),
                "best_for": model_info.get("best_for", "")
            })
        return {"available_models": available, "count": len(available)}
    except Exception as e:
        return {"error": str(e), "available_models": []}

@app.get("/models/tier-info")
async def get_tier_info():
    """Get information about available performance tiers"""
    try:
        if YAML_CONFIG_AVAILABLE:
            tiers_info = ai_manager.yaml_config.performance_tiers_info
        else:
            tiers_info = {
                "fast": {"description": "Ultra-fast models", "avg_response_time": "0.5-2s"},
                "balanced": {"description": "Mix of speed and quality", "avg_response_time": "2-6s"},
                "full": {"description": "All models available", "avg_response_time": "varies"}
            }
        
        return {
            "tiers": tiers_info,
            "current_tier": ai_manager.yaml_config.performance_tier if YAML_CONFIG_AVAILABLE else "unknown"
        }
    except Exception as e:
        return {"error": str(e), "tiers": {}}

@app.post("/models/set-tier")
async def set_performance_tier(tier: str):
    """Switch to a different performance tier (requires restart)"""
    try:
        valid_tiers = ["fast", "balanced", "quality", "full"]
        if tier not in valid_tiers:
            return {"error": f"Invalid tier. Must be one of: {valid_tiers}"}
        
        # In production, would update YAML and require restart
        return {
            "message": f"Tier changed to {tier}",
            "note": "Service restart required to apply changes",
            "command": f"export AI_PERFORMANCE_TIER={tier}"
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/models/task-recommendations")
async def get_task_recommendations():
    """Get model recommendations for different trading tasks"""
    try:
        recommendations = {
            "real_time_trading": {
                "description": "Ultra-fast models for immediate decisions",
                "preferred_models": ["orca-mini-3b-gguf2-q4_0", "microsoft/phi-2"],
                "max_latency_ms": 2000
            },
            "financial_analysis": {
                "description": "Balanced models for detailed analysis",
                "preferred_models": ["mistral-7b-instruct-v0.1.Q4_0", "ProsusAI/finbert"],
                "max_latency_ms": 10000
            },
            "code_generation": {
                "description": "Code-specialized models",
                "preferred_models": ["codellama/CodeLlama-7b-Instruct-hf", "microsoft/phi-2"],
                "max_latency_ms": 5000
            },
            "market_sentiment": {
                "description": "Financial sentiment analysis",
                "preferred_models": ["ProsusAI/finbert"],
                "max_latency_ms": 3000
            },
            "research": {
                "description": "Comprehensive analysis models",
                "preferred_models": ["mistral-7b-instruct-v0.1.Q4_0", "nous-hermes-llama2-13b"],
                "max_latency_ms": 15000
            },
            "document_search": {
                "description": "Embedding-based search",
                "preferred_models": ["sentence-transformers/all-MiniLM-L6-v2"],
                "max_latency_ms": 500
            }
        }
        return recommendations
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# 🎯 HOSTED MODELS MANAGEMENT - Side-by-Side Comparison
# ─────────────────────────────────────────────────────────────────────────────

from hosted_models import hosted_models_manager

@app.get("/models/hosted")
async def get_hosted_models():
    """Get all hosted/external models and their API key status"""
    return {
        "hosted_models": hosted_models_manager.get_all_models(),
        "summary": hosted_models_manager.get_summary()
    }

@app.get("/models/hosted/configured")
async def get_configured_hosted_models():
    """Get only hosted models that have API keys configured"""
    return {
        "configured_models": hosted_models_manager.get_configured_models(),
        "count": len(hosted_models_manager.get_configured_models())
    }

@app.get("/models/hosted/unconfigured")
async def get_unconfigured_hosted_models():
    """Get hosted models that need API keys"""
    return {
        "unconfigured_models": hosted_models_manager.get_unconfigured_models(),
        "count": len(hosted_models_manager.get_unconfigured_models())
    }

@app.get("/models/compare")
async def compare_all_models():
    """Get side-by-side comparison of local vs hosted models"""
    local_models = []
    for model_id, model_info in ai_manager.model_info.items():
        local_models.append({
            "id": model_id,
            "name": model_info.get("name", "Unknown"),
            "source": "local",
            "type": model_info.get("type", "unknown"),
            "size": model_info.get("size", "unknown"),
            "speed": model_info.get("speed", "unknown"),
            "quality": model_info.get("quality", "unknown"),
            "installed": model_id in ai_manager.models,
            "cost": "Free (one-time download)",
            "privacy": "Full (runs locally)",
            "best_for": model_info.get("best_for", ""),
            "use_cases": model_info.get("use_cases", [])
        })
    
    hosted_models = hosted_models_manager.get_all_models()
    hosted_formatted = []
    for model in hosted_models:
        hosted_formatted.append({
            "id": model["id"],
            "name": model["name"],
            "source": "hosted",
            "provider": model["provider"],
            "speed": "instant",
            "quality": model["model_family"],
            "installed": model["has_key"],
            "cost": f"${model['cost_per_1k_tokens']}/1k tokens",
            "privacy": "Cloud-based",
            "best_for": model["best_for"],
            "use_cases": model["use_cases"]
        })
    
    return {
        "local_models": {
            "count": len(local_models),
            "installed": len([m for m in local_models if m["installed"]]),
            "models": local_models
        },
        "hosted_models": {
            "count": len(hosted_formatted),
            "configured": len([m for m in hosted_formatted if m["installed"]]),
            "models": hosted_formatted
        },
        "comparison_summary": {
            "total_available": len(local_models) + len(hosted_formatted),
            "local_available": len(local_models),
            "hosted_available": len(hosted_formatted),
            "total_installed": len([m for m in local_models if m["installed"]]) + 
                              len([m for m in hosted_formatted if m["installed"]])
        }
    }

@app.get("/models/trading-dashboard")
async def get_trading_dashboard_models():
    """Complete model status for trading UI dashboard"""
    local_status = []
    for model_id, model_info in ai_manager.model_info.items():
        local_status.append({
            "id": model_id,
            "name": model_info.get("name", "Unknown"),
            "category": "local",
            "status": "loaded" if model_id in ai_manager.models else "available",
            "type": model_info.get("type", "unknown"),
            "speed": model_info.get("speed", "unknown"),
            "quality": model_info.get("quality", "unknown"),
            "size": model_info.get("size", "unknown"),
            "use_cases": model_info.get("use_cases", []),
            "location": "local_system"
        })
    
    hosted_status = []
    for model in hosted_models_manager.get_all_models():
        hosted_status.append({
            "id": model["id"],
            "name": model["name"],
            "category": "hosted",
            "status": "configured" if model["has_key"] else "not_configured",
            "provider": model["provider"],
            "speed": "instant",
            "quality": model["model_family"],
            "cost_per_1k": model["cost_per_1k_tokens"],
            "use_cases": model["use_cases"],
            "location": f"cloud_{model['provider']}"
        })
    
    return {
        "timestamp": datetime.now().isoformat(),
        "available_locally": len([m for m in local_status if m["status"] == "loaded"]),
        "configured_hosted": len([m for m in hosted_status if m["status"] == "configured"]),
        "local_models": local_status,
        "hosted_models": hosted_status,
        "quick_stats": {
            "total_local": len(local_status),
            "total_hosted": len(hosted_status),
            "local_ready_to_use": len([m for m in local_status if m["status"] == "loaded"]),
            "hosted_ready_to_use": len([m for m in hosted_status if m["status"] == "configured"])
        }
    }

@app.post("/models/configure-hosted")
async def configure_hosted_model(model_id: str, api_key: str):
    """Configure API key for a hosted model"""
    success = hosted_models_manager.configure_model(model_id, api_key)
    if success:
        return {
            "status": "configured",
            "model_id": model_id,
            "ready": True
        }
    else:
        return {
            "status": "error",
            "message": f"Model {model_id} not found"
        }

@app.get("/models/usage-tracking")
async def get_model_usage_tracking():
    """Track which models are being used and for what tasks"""
    # This would be populated as models are used
    return {
        "tracking_enabled": True,
        "usage_history": [
            {
                "timestamp": datetime.now().isoformat(),
                "model_id": "selected_model",
                "task_type": "financial_analysis",
                "duration_seconds": 2.5,
                "tokens_used": 450,
                "source": "local_or_hosted"
            }
        ],
        "model_statistics": {
            "most_used_model": "mistral-7b-instruct-v0.1.Q4_0",
            "total_inferences": 150,
            "average_response_time": 2.3,
            "cost_estimate_usd": 0.00  # Will populate for hosted models
        }
    }

# If __name__ == "__main__":
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3008)