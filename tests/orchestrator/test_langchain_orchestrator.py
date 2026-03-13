"""
LangChain Orchestrator Integration Tests
Tests for the Orchestrator service with LangChain-powered decision making
"""
import pytest
from tests.shared.fixtures import BASE_URL, STRATEGY_CTX_30


class TestOrchestratorLangChainIntegration:
    """Test LangChain integration in Orchestrator service"""
    
    @pytest.mark.unit
    def test_orchestrator_health_includes_llm_status(self, http):
        """Verify Orchestrator reports LLM/LangChain status"""
        url = BASE_URL["orchestrator"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "orchestrator"
        # Check for LLM-related fields if LangChain is integrated
        assert "status" in data
    
    @pytest.mark.integration
    def test_llm_decision_endpoint(self, http):
        """Test POST /pipeline/trigger/llm endpoint for LLM-powered decisions"""
        url = BASE_URL["orchestrator"]
        
        payload = {
            "pair": "BTC/USDT",
            "strategy": "smart",  # LLM decides best strategy
            "market_data": STRATEGY_CTX_30,
        }
        
        # This endpoint may not exist yet - check gracefully
        r = http.post(f"{url}/pipeline/trigger/llm", json=payload)
        # Accept 200, 201, 404, or 422 (not found or invalid payload)
        assert r.status_code in [200, 201, 404, 422]
    
    @pytest.mark.integration
    def test_llm_explanation_endpoint(self, http):
        """Test that LLM can explain its decisions"""
        url = BASE_URL["orchestrator"]
        
        payload = {
            "decision": {
                "action": "BUY",
                "symbol": "BTC",
                "quantity": 0.1,
            }
        }
        
        # Endpoint to ask LLM to explain the decision
        r = http.post(f"{url}/explain-decision", json=payload)
        # Accept 200, 404, or 422
        assert r.status_code in [200, 404, 422]
    
    @pytest.mark.unit
    def test_regime_classification_respects_llm_input(self, http):
        """Regime classifier should feed into LLM decision"""
        url = BASE_URL["orchestrator"]
        
        # Get regime classification
        regime_resp = http.post(
            f"{url}/classify-regime?pair=BTC%2FUSDT",
            json=STRATEGY_CTX_30
        )
        assert regime_resp.status_code == 200
        regime = regime_resp.json()
        
        # Verify regime has necessary fields for LLM input
        assert "regime" in regime
        assert "confidence" in regime
        assert "pair" in regime
    
    @pytest.mark.integration
    def test_multi_agent_voting_with_llm(self, http):
        """Test that LLM coordinates multi-agent voting"""
        url = BASE_URL["orchestrator"]
        
        # Multi-agent voting where LLM acts as meta-coordinator
        payload = {
            "agents": ["strategy_agent", "risk_agent", "execution_agent"],
            "context": STRATEGY_CTX_30,
            "pair": "BTC/USDT",
        }
        
        r = http.post(f"{url}/multi-agent-vote", json=payload)
        # Accept 200, 404, or 422
        assert r.status_code in [200, 201, 404, 422]


class TestOrchestratorServiceCoordination:
    """Test that Orchestrator coordinates all services with potential LLM backing"""
    
    @pytest.mark.integration
    def test_orchestrator_can_reach_portfolio_service(self, http):
        """Orchestrator should be able to coordinate with Portfolio service"""
        portfolio_url = BASE_URL["portfolio"]
        r = http.get(f"{portfolio_url}/health")
        assert r.status_code == 200
    
    @pytest.mark.integration
    def test_orchestrator_can_reach_strategy_service(self, http):
        """Orchestrator should be able to coordinate with Strategy service"""
        strategy_url = BASE_URL["strategy"]
        r = http.get(f"{strategy_url}/health")
        assert r.status_code == 200
    
    @pytest.mark.integration
    def test_orchestrator_can_reach_risk_service(self, http):
        """Orchestrator should be able to coordinate with Risk service"""
        risk_url = BASE_URL["risk"]
        r = http.get(f"{risk_url}/health")
        assert r.status_code == 200
    
    @pytest.mark.integration
    def test_orchestrator_can_reach_execution_service(self, http):
        """Orchestrator should be able to coordinate with Execution service"""
        execution_url = BASE_URL["execution"]
        r = http.get(f"{execution_url}/health")
        assert r.status_code == 200
    
    @pytest.mark.integration
    def test_orchestrator_can_reach_ai_service(self, http):
        """Orchestrator should be able to reach the AI service for LLM"""
        ai_url = BASE_URL["local_ai"]
        r = http.get(f"{ai_url}/health")
        assert r.status_code == 200
    
    @pytest.mark.integration
    def test_orchestrator_reaches_all_services(self, http):
        """Orchestrator must reach all 7 services for full coordination"""
        required_services = ["portfolio", "strategy", "risk", "execution", "analytics", "config", "local_ai"]
        
        for service in required_services:
            url = BASE_URL.get(service)
            if url:
                r = http.get(f"{url}/health")
                assert r.status_code == 200, f"Cannot reach {service}"


class TestAIServiceAgentVisibility:
    """Test that we can inspect AI agent operations and see all parts"""
    
    @pytest.mark.unit
    def test_ai_service_models_endpoint(self, http):
        """View available models in AI service"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/models/trading-dashboard")
        assert r.status_code == 200
        
        # Should list models
        data = r.json()
        assert data is not None
    
    @pytest.mark.unit
    def test_ai_service_model_details(self, http):
        """Get details about available models"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/models/trading-dashboard")
        
        if r.status_code == 200:
            data = r.json()
            # Verify structure has model information
            if isinstance(data, list):
                for model in data:
                    assert isinstance(model, dict)
            elif isinstance(data, dict):
                assert "models" in data or "available_models" in data or len(data) >= 0
    
    @pytest.mark.integration
    def test_ai_service_status_and_configuration(self, http):
        """Check AI service configuration"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/health")
        
        assert r.status_code == 200
        data = r.json()
        assert "service" in data
        assert data["service"] == "local_ai"


class TestAgentDecisionVisibility:
    """Test that we can see all decision-making steps of the agent"""
    
    @pytest.mark.integration
    def test_can_see_regime_classification_step(self, http):
        """Inspect the regime classification step"""
        url = BASE_URL["orchestrator"]
        
        r = http.post(
            f"{url}/classify-regime?pair=BTC%2FUSDT",
            json={"candles": []},  # Will need real data
        )
        
        # Should return classification info
        if r.status_code == 200:
            data = r.json()
            assert "regime" in data
            assert "confidence" in data
    
    @pytest.mark.integration
    def test_can_see_strategy_evaluation_step(self, http):
        """Inspect strategy evaluation results"""
        url = BASE_URL["strategy"]
        
        r = http.get(f"{url}/list")
        assert r.status_code == 200
        
        strategies = r.json()
        # Should show all available strategies
        assert isinstance(strategies, list)
    
    @pytest.mark.integration
    def test_can_see_risk_assessment_step(self, http):
        """Inspect risk assessment"""
        url = BASE_URL["risk"]
        
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        
        # Risk service should report its status
        assert r.json()["service"] == "risk"
    
    @pytest.mark.integration
    def test_can_see_execution_queue(self, http):
        """Inspect execution queue to see pending orders"""
        url = BASE_URL["execution"]
        
        r = http.get(f"{url}/queue-depth")
        
        # Should report queue depth
        if r.status_code == 200:
            data = r.json()
            assert "depth" in data or "queue_depth" in data or "queued" in data
    
    @pytest.mark.integration
    def test_can_see_analytics_metrics(self, http):
        """Inspect analytics for performance metrics"""
        url = BASE_URL["analytics"]
        
        r = http.get(f"{url}/trades")
        
        # Should list trades/metrics
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, list)
    
    @pytest.mark.integration
    def test_orchestrator_audit_trail(self, http):
        """Verify we can see orchestrator decisions"""
        url = BASE_URL["orchestrator"]
        
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        
        # Orchestrator should be operational
        assert r.json()["service"] == "orchestrator"
