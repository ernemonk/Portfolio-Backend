"""
YAML-driven Model Configuration Loader
Replaces the hardcoded ModelConfig with dynamic YAML-based configuration
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class YAMLModelConfig:
    def __init__(self, config_path: str = "/app/models.yml"):
        self.config_path = config_path
        self.config = self._load_config()
        
        # Environment-driven settings
        self.performance_tier = os.getenv("AI_PERFORMANCE_TIER", "balanced")
        self.auto_download = os.getenv("AI_AUTO_DOWNLOAD", "true").lower() == "true"
        self.preload_models = os.getenv("AI_PRELOAD_MODELS", "true").lower() == "true"
        self.max_memory_gb = int(os.getenv("AI_MAX_MEMORY_GB", "8"))
        
        logger.info(f"🎯 AI Config: {self.performance_tier} tier, auto_download={self.auto_download}")

    def _load_config(self) -> Dict:
        """Load YAML configuration"""
        try:
            with open(self.config_path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"✅ Loaded AI config from {self.config_path}")
                return config
        except FileNotFoundError:
            logger.warning(f"⚠️  Config file {self.config_path} not found, using defaults")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Fallback configuration if YAML not found"""
        return {
            "model_config": {
                "performance_tiers": {
                    "balanced": {
                        "models": [
                            {"id": "orca-mini-3b-gguf2-q4_0", "type": "gpt4all", "priority": 1},
                            {"id": "sentence-transformers/all-MiniLM-L6-v2", "type": "embeddings", "priority": 1}
                        ]
                    }
                }
            }
        }

    @property
    def current_tier_config(self) -> Dict:
        """Get configuration for current performance tier"""
        tiers = self.config.get("model_config", {}).get("performance_tiers", {})
        return tiers.get(self.performance_tier, tiers.get("balanced", {}))

    @property
    def models_for_tier(self) -> List[Dict]:
        """Get models for current performance tier"""
        return self.current_tier_config.get("models", [])

    @property
    def priority_models(self) -> List[Dict]:
        """Get priority 1 models for preloading"""
        return [model for model in self.models_for_tier if model.get("priority", 2) == 1]

    @property
    def optimized_models(self) -> Dict[str, Dict]:
        """Convert to format expected by LocalAIManager"""
        models = {}
        
        for model in self.models_for_tier:
            model_id = model["id"]
            models[model_id] = {
                "id": model_id,
                "name": model.get("name", model_id),
                "type": model["type"],
                "size": model.get("size", "Unknown"),
                "priority": model.get("priority", 2),
                "use_cases": model.get("use_cases", []),
                "category": self.performance_tier
            }
            
        return models

    def get_environment_config(self) -> Dict:
        """Get environment configuration"""
        env_config = self.config.get("environment", {})
        
        return {
            "cache_dir": env_config.get("cache_dir", "/root/.trading_os/model_cache"),
            "models_dir": env_config.get("models_dir", "/root/.trading_os/ai_models"),
            "optimizations": env_config.get("optimizations", {}),
            "resource_limits": env_config.get("resource_limits", {})
        }

    def get_tier_info(self) -> Dict:
        """Get information about current performance tier"""
        tier_config = self.current_tier_config
        
        return {
            "tier": self.performance_tier,
            "description": tier_config.get("description", ""),
            "total_size_gb": tier_config.get("total_size_gb", 0),
            "avg_response_time": tier_config.get("avg_response_time", "Unknown"),
            "model_count": len(self.models_for_tier),
            "priority_models": len(self.priority_models)
        }

    def switch_tier(self, new_tier: str) -> bool:
        """Switch to a different performance tier"""
        available_tiers = list(self.config.get("model_config", {}).get("performance_tiers", {}).keys())
        
        if new_tier not in available_tiers:
            logger.error(f"❌ Invalid tier '{new_tier}'. Available: {available_tiers}")
            return False
            
        self.performance_tier = new_tier
        logger.info(f"🎯 Switched to {new_tier} tier")
        return True

    def get_available_tiers(self) -> List[str]:
        """Get list of available performance tiers"""
        return list(self.config.get("model_config", {}).get("performance_tiers", {}).keys())

    def print_config_summary(self):
        """Print current configuration summary"""
        tier_info = self.get_tier_info()
        
        print(f"🎯 TRADING OS AI - {tier_info['tier'].upper()} TIER")
        print("═" * 50)
        print(f"📊 Description: {tier_info['description']}")
        print(f"📦 Models: {tier_info['model_count']} ({tier_info['priority_models']} priority)")
        print(f"💾 Total Size: {tier_info['total_size_gb']}GB")
        print(f"⚡ Response Time: {tier_info['avg_response_time']}")
        print(f"🚀 Auto Download: {self.auto_download}")
        print(f"🔥 Preload Models: {self.preload_models}")
        print()
        
        print("📋 Models in this tier:")
        for i, model in enumerate(self.models_for_tier, 1):
            priority_icon = "🔥" if model.get("priority", 2) == 1 else "⭐"
            print(f"  {i}. {priority_icon} {model.get('name', model['id'])} ({model['type']})")
        print()