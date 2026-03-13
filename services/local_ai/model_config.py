"""
Optimized Model Configuration for Trading OS Local AI

This configuration provides the best mix of speed and quality models,
organized by use case and performance characteristics.
"""

import os
from pathlib import Path
from typing import Dict, List, Any

class ModelConfig:
    def __init__(self):
        self.models_dir = Path.home() / ".trading_os" / "ai_models"
        self.cache_dir = Path.home() / ".trading_os" / "model_cache"
        
        # Create directories
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def optimized_models(self) -> Dict[str, Dict[str, Any]]:
        """
        Curated selection of best-performing models by category
        
        Categories:
        - fast: Ultra-fast responses, good for real-time trading decisions
        - balanced: Best mix of speed and quality 
        - quality: Highest quality responses, slower but more accurate
        - specialized: Task-specific models (embeddings, analysis, etc.)
        """
        return {
            # ═══════════════════════════════════════════════════════════
            # FAST MODELS - Sub-second responses
            # ═══════════════════════════════════════════════════════════
            "orca-mini-3b-gguf2-q4_0": {
                "id": "orca-mini-3b-gguf2-q4_0",
                "name": "Orca Mini 3B (Fast)",
                "category": "fast", 
                "size": "1.9GB",
                "speed": "⚡ Ultra Fast",
                "quality": "⭐⭐⭐",
                "type": "gpt4all",
                "use_cases": ["real-time trading decisions", "quick analysis", "chat"],
                "avg_response_time": "0.5-1.5s",
                "description": "Lightning fast for real-time trading insights"
            },
            
            "phi-2": {
                "id": "microsoft/phi-2", 
                "name": "Microsoft Phi-2 (Optimized)",
                "category": "fast",
                "size": "2.7GB",
                "speed": "⚡ Ultra Fast", 
                "quality": "⭐⭐⭐⭐",
                "type": "transformers",
                "use_cases": ["code analysis", "quick reasoning", "trading logic"],
                "avg_response_time": "0.8-2s", 
                "description": "Microsoft's optimized small model, excellent reasoning"
            },

            # ═══════════════════════════════════════════════════════════
            # BALANCED MODELS - Best overall performance 
            # ═══════════════════════════════════════════════════════════
            "mistral-7b-instruct-v0.1.Q4_0": {
                "id": "mistral-7b-instruct-v0.1.Q4_0",
                "name": "Mistral 7B Instruct (Balanced)", 
                "category": "balanced",
                "size": "4.1GB",
                "speed": "🚀 Fast",
                "quality": "⭐⭐⭐⭐⭐",
                "type": "gpt4all", 
                "use_cases": ["financial analysis", "strategy planning", "comprehensive reports"],
                "avg_response_time": "2-5s",
                "description": "Perfect balance of speed and intelligence for trading"
            },
            
            "code-llama-7b-instruct": {
                "id": "codellama/CodeLlama-7b-Instruct-hf",
                "name": "Code Llama 7B Instruct",
                "category": "balanced", 
                "size": "13GB",
                "speed": "🚀 Fast",
                "quality": "⭐⭐⭐⭐⭐",
                "type": "transformers",
                "use_cases": ["trading strategy code", "backtesting scripts", "API integrations"],
                "avg_response_time": "3-6s",
                "description": "Meta's code specialist, excellent for trading algorithms"
            },

            # ═══════════════════════════════════════════════════════════
            # QUALITY MODELS - Highest intelligence
            # ═══════════════════════════════════════════════════════════ 
            "nous-hermes-llama2-13b.q4_0": {
                "id": "nous-hermes-llama2-13b.q4_0", 
                "name": "Nous Hermes Llama2 13B (Quality)",
                "category": "quality",
                "size": "7.3GB", 
                "speed": "🐢 Slower",
                "quality": "⭐⭐⭐⭐⭐⭐",
                "type": "gpt4all",
                "use_cases": ["complex financial modeling", "detailed reports", "research"],
                "avg_response_time": "5-15s",
                "description": "Highest quality responses for complex trading analysis"
            },
            
            "dolphin-mixtral-8x7b": {
                "id": "cognitivecomputations/dolphin-2.6-mixtral-8x7b",
                "name": "Dolphin Mixtral 8x7B (Premium)",
                "category": "quality",
                "size": "26GB",
                "speed": "🐢 Slower", 
                "quality": "⭐⭐⭐⭐⭐⭐⭐",
                "type": "transformers",
                "use_cases": ["advanced portfolio optimization", "risk modeling", "research"],
                "avg_response_time": "10-30s",
                "description": "Mixture of experts model, exceptional reasoning"
            },

            # ═══════════════════════════════════════════════════════════
            # SPECIALIZED MODELS - Task-specific 
            # ═══════════════════════════════════════════════════════════
            "all-MiniLM-L6-v2": {
                "id": "sentence-transformers/all-MiniLM-L6-v2",
                "name": "MiniLM Embeddings (Specialized)",
                "category": "specialized",
                "size": "80MB",
                "speed": "⚡ Ultra Fast",
                "quality": "⭐⭐⭐⭐⭐",
                "type": "embeddings",
                "use_cases": ["document similarity", "semantic search", "clustering"],
                "avg_response_time": "0.1-0.5s", 
                "description": "Lightning-fast embeddings for document analysis"
            },
            
            "finbert": {
                "id": "ProsusAI/finbert",
                "name": "FinBERT (Financial Specialist)",
                "category": "specialized", 
                "size": "400MB",
                "speed": "⚡ Fast",
                "quality": "⭐⭐⭐⭐⭐⭐",
                "type": "transformers",
                "use_cases": ["financial sentiment", "market analysis", "news processing"],
                "avg_response_time": "1-3s",
                "description": "Pre-trained on financial data, expert in market language"
            }
        }

    def get_recommended_setup(self, performance_tier: str = "balanced") -> List[str]:
        """
        Get recommended models based on performance requirements
        
        Args:
            performance_tier: "fast", "balanced", "quality", or "full"
        """
        models = self.optimized_models
        
        setups = {
            "fast": [
                "orca-mini-3b-gguf2-q4_0",     # Ultra-fast general
                "phi-2",                        # Fast reasoning
                "all-MiniLM-L6-v2"             # Fast embeddings
            ],
            "balanced": [
                "mistral-7b-instruct-v0.1.Q4_0",  # Main workhorse  
                "phi-2",                           # Fast secondary
                "finbert",                         # Financial specialist
                "all-MiniLM-L6-v2"                # Embeddings
            ],
            "quality": [
                "nous-hermes-llama2-13b.q4_0",    # High quality general
                "code-llama-7b-instruct",          # Code specialist
                "finbert",                         # Financial specialist
                "all-MiniLM-L6-v2"                # Embeddings  
            ],
            "full": list(models.keys())  # All models
        }
        
        return setups.get(performance_tier, setups["balanced"])

    def get_install_commands(self, model_ids: List[str]) -> List[str]:
        """Generate optimized installation commands"""
        commands = []
        
        # Set up optimization environment variables
        commands.extend([
            "export HF_HOME=$HOME/.trading_os/model_cache",
            "export TRANSFORMERS_CACHE=$HOME/.trading_os/model_cache", 
            "export HF_DATASETS_CACHE=$HOME/.trading_os/model_cache",
            "export TORCH_HOME=$HOME/.trading_os/model_cache"
        ])
        
        # Pre-download models with caching
        for model_id in model_ids:
            model = self.optimized_models.get(model_id)
            if model:
                if model["type"] == "gpt4all":
                    commands.append(f"python -c \"from gpt4all import GPT4All; GPT4All('{model_id}', model_path='{self.models_dir}')\"")
                elif model["type"] == "transformers":
                    commands.append(f"python -c \"from transformers import AutoTokenizer, AutoModelForCausalLM; AutoTokenizer.from_pretrained('{model_id}', cache_dir='{self.cache_dir}'); AutoModelForCausalLM.from_pretrained('{model_id}', cache_dir='{self.cache_dir}')\"")
                elif model["type"] == "embeddings":
                    commands.append(f"python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('{model_id}', cache_folder='{self.cache_dir}')\"")
        
        return commands

    def print_setup_guide(self, performance_tier: str = "balanced"):
        """Print a comprehensive setup guide"""
        recommended = self.get_recommended_setup(performance_tier)
        total_size = sum(
            float(self.optimized_models[mid]["size"].replace("GB", "").replace("MB", "0.001"))
            for mid in recommended if mid in self.optimized_models
        )
        
        print(f"🚀 TRADING OS AI SETUP - {performance_tier.upper()} TIER")
        print(f"═══════════════════════════════════════════════════════")
        print(f"📦 Total Models: {len(recommended)}")
        print(f"💾 Total Size: ~{total_size:.1f}GB") 
        print(f"⚡ Performance Focus: {performance_tier.title()}")
        print()
        
        for i, model_id in enumerate(recommended, 1):
            if model_id in self.optimized_models:
                model = self.optimized_models[model_id]
                print(f"{i}. {model['name']}")
                print(f"   📊 {model['speed']} | 🎯 {model['quality']} | 💾 {model['size']}")
                print(f"   🎯 Use: {', '.join(model['use_cases'][:2])}")
                print(f"   ⏱️  Response: {model['avg_response_time']}")
                print()