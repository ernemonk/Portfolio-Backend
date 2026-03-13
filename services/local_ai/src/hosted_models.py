"""
Hosted Models Configuration & Key Management
For external API-based models (OpenAI, Claude, etc.)
"""

import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class HostedModel:
    id: str
    name: str
    provider: str  # "openai", "anthropic", "cohere", etc.
    model_family: str
    cost_per_1k_tokens: float
    api_key_env_var: str
    has_key: bool
    status: str  # "configured", "unconfigured", "invalid"
    use_cases: List[str]
    best_for: str
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model_family": self.model_family,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "has_key": self.has_key,
            "status": self.status,
            "use_cases": self.use_cases,
            "best_for": self.best_for
        }

class HostedModelsManager:
    """Manage hosted/external AI models and API keys"""
    
    def __init__(self):
        self.models: Dict[str, HostedModel] = self._initialize_models()
    
    def _initialize_models(self) -> Dict[str, HostedModel]:
        """Initialize known hosted models"""
        models = {}
        
        # OpenAI Models
        models["gpt-4"] = HostedModel(
            id="gpt-4",
            name="GPT-4",
            provider="openai",
            model_family="GPT-4",
            cost_per_1k_tokens=0.03,
            api_key_env_var="OPENAI_API_KEY",
            has_key=self._check_api_key("OPENAI_API_KEY"),
            status=self._get_status("OPENAI_API_KEY"),
            use_cases=["financial_analysis", "research", "complex_reasoning"],
            best_for="Complex financial analysis & strategic decisions"
        )
        
        models["gpt-3.5-turbo"] = HostedModel(
            id="gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            provider="openai",
            model_family="GPT-3.5",
            cost_per_1k_tokens=0.002,
            api_key_env_var="OPENAI_API_KEY",
            has_key=self._check_api_key("OPENAI_API_KEY"),
            status=self._get_status("OPENAI_API_KEY"),
            use_cases=["quick_analysis", "summarization", "general_chat"],
            best_for="Fast, cost-effective analysis"
        )
        
        # Anthropic Models
        models["claude-3-opus"] = HostedModel(
            id="claude-3-opus",
            name="Claude 3 Opus",
            provider="anthropic",
            model_family="Claude 3",
            cost_per_1k_tokens=0.015,
            api_key_env_var="ANTHROPIC_API_KEY",
            has_key=self._check_api_key("ANTHROPIC_API_KEY"),
            status=self._get_status("ANTHROPIC_API_KEY"),
            use_cases=["detailed_analysis", "research", "strategy"],
            best_for="Detailed financial research & strategy"
        )
        
        models["claude-3-sonnet"] = HostedModel(
            id="claude-3-sonnet",
            name="Claude 3 Sonnet",
            provider="anthropic",
            model_family="Claude 3",
            cost_per_1k_tokens=0.003,
            api_key_env_var="ANTHROPIC_API_KEY",
            has_key=self._check_api_key("ANTHROPIC_API_KEY"),
            status=self._get_status("ANTHROPIC_API_KEY"),
            use_cases=["balanced_analysis", "quick_responses"],
            best_for="Balanced speed and quality"
        )
        
        # Cohere Models
        models["command-r-plus"] = HostedModel(
            id="command-r-plus",
            name="Command R+",
            provider="cohere",
            model_family="Command R",
            cost_per_1k_tokens=0.01,
            api_key_env_var="COHERE_API_KEY",
            has_key=self._check_api_key("COHERE_API_KEY"),
            status=self._get_status("COHERE_API_KEY"),
            use_cases=["market_analysis", "trading_signals"],
            best_for="Market analysis & trading signals"
        )
        
        return models
    
    @staticmethod
    def _check_api_key(env_var: str) -> bool:
        """Check if API key environment variable is set"""
        key = os.getenv(env_var, "").strip()
        return bool(key and len(key) > 10)
    
    @staticmethod
    def _get_status(env_var: str) -> str:
        """Determine status of API key"""
        key = os.getenv(env_var, "").strip()
        if not key:
            return "unconfigured"
        elif len(key) > 10:
            return "configured"
        else:
            return "invalid"
    
    def get_all_models(self) -> List[Dict]:
        """Get all hosted models with their status"""
        return [model.to_dict() for model in self.models.values()]
    
    def get_models_by_provider(self, provider: str) -> List[Dict]:
        """Get models filtered by provider"""
        return [
            model.to_dict() 
            for model in self.models.values() 
            if model.provider == provider
        ]
    
    def get_configured_models(self) -> List[Dict]:
        """Get only models with API keys configured"""
        return [
            model.to_dict() 
            for model in self.models.values() 
            if model.has_key
        ]
    
    def get_unconfigured_models(self) -> List[Dict]:
        """Get models without API keys"""
        return [
            model.to_dict() 
            for model in self.models.values() 
            if not model.has_key
        ]
    
    def configure_model(self, model_id: str, api_key: str) -> bool:
        """Set API key for a model"""
        if model_id not in self.models:
            return False
        
        model = self.models[model_id]
        os.environ[model.api_key_env_var] = api_key
        model.has_key = len(api_key) > 10
        model.status = "configured" if model.has_key else "invalid"
        return True
    
    def get_summary(self) -> Dict:
        """Get summary of all models and their status"""
        configured = [m for m in self.models.values() if m.has_key]
        unconfigured = [m for m in self.models.values() if not m.has_key]
        
        return {
            "total_hosted_models": len(self.models),
            "configured_count": len(configured),
            "unconfigured_count": len(unconfigured),
            "providers": list(set(m.provider for m in self.models.values())),
            "configured_models": [m.to_dict() for m in configured],
            "unconfigured_models": [m.to_dict() for m in unconfigured]
        }

# Initialize manager
hosted_models_manager = HostedModelsManager()
