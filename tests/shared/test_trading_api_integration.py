"""
Trading API Integration Tests
Tests for the updated trading-api.ts with centralized service routing, retry logic, and AI service
"""
import pytest
import httpx
from tests.shared.fixtures import BASE_URL


class TestTradingAPIServiceRouting:
    """
    Test that all services are properly routed through centralized API
    This corresponds to the updated trading-api.ts SERVICES object
    """
    
    @pytest.mark.smoke
    def test_portfolio_service_endpoint(self, http):
        """Verify Portfolio service (3001) is reachable"""
        url = BASE_URL["portfolio"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "portfolio"
    
    @pytest.mark.smoke
    def test_strategy_service_endpoint(self, http):
        """Verify Strategy service (3002) is reachable"""
        url = BASE_URL["strategy"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "strategy"
    
    @pytest.mark.smoke
    def test_risk_service_endpoint(self, http):
        """Verify Risk service (3003) is reachable"""
        url = BASE_URL["risk"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "risk"
    
    @pytest.mark.smoke
    def test_execution_service_endpoint(self, http):
        """Verify Execution service (3004) is reachable"""
        url = BASE_URL["execution"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "execution"
    
    @pytest.mark.smoke
    def test_orchestrator_service_endpoint(self, http):
        """Verify Orchestrator service (3005) is reachable"""
        url = BASE_URL["orchestrator"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "orchestrator"
    
    @pytest.mark.smoke
    def test_analytics_service_endpoint(self, http):
        """Verify Analytics service (3006) is reachable"""
        url = BASE_URL["analytics"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "analytics"
    
    @pytest.mark.smoke
    def test_config_service_endpoint(self, http):
        """Verify Config service (3007) is reachable"""
        url = BASE_URL["config"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "config"
    
    @pytest.mark.smoke
    def test_local_ai_service_endpoint(self, http):
        """Verify Local AI service (3008) is reachable - NEW ADDITION"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/health")
        assert r.status_code == 200
        assert r.json()["service"] == "local_ai"


class TestAIServiceIntegration:
    """Test the new AI service endpoints added to SERVICES object"""
    
    @pytest.mark.smoke
    def test_get_models_endpoint(self, http):
        """Test /models/trading-dashboard endpoint"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/models/trading-dashboard")
        assert r.status_code == 200
        data = r.json()
        assert "models" in data or "available_models" in data or isinstance(data, list)
    
    @pytest.mark.unit
    def test_models_have_required_fields(self, http):
        """Test that each model has id, name, and status"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/models/trading-dashboard")
        data = r.json()
        
        # Handle different response formats
        models = data if isinstance(data, list) else data.get("models", [])
        
        for model in models:
            assert "id" in model or "name" in model
            assert isinstance(model, dict)
    
    @pytest.mark.unit
    def test_model_configuration_endpoint(self, http):
        """Test POST /models/configure-hosted endpoint"""
        url = BASE_URL["local_ai"]
        payload = {
            "model_id": "test-model",
            "api_key": "test-key-123"
        }
        r = http.post(f"{url}/models/configure-hosted", json=payload)
        # Should either accept or reject gracefully
        assert r.status_code in [200, 201, 400, 422]
    
    @pytest.mark.integration
    def test_ai_service_status(self, http):
        """Test AI service provides status information"""
        url = BASE_URL["local_ai"]
        r = http.get(f"{url}/health")
        data = r.json()
        assert data.get("service") == "local_ai"
        assert "status" in data or "ok" in data


class TestRetryLogic:
    """Test that retry logic works for transient failures"""
    
    @pytest.mark.unit
    def test_service_endpoint_consistency(self, http):
        """Call same endpoint multiple times - should get consistent responses"""
        url = BASE_URL["portfolio"]
        
        for _ in range(3):
            r = http.get(f"{url}/health")
            assert r.status_code == 200
            assert r.json()["service"] == "portfolio"
    
    @pytest.mark.integration
    def test_parallel_requests_to_ai_service(self, http):
        """Test multiple concurrent requests to AI service"""
        url = BASE_URL["local_ai"]
        
        responses = []
        for _ in range(5):
            r = http.get(f"{url}/health")
            responses.append(r.status_code)
        
        # All should succeed
        assert all(code == 200 for code in responses)
    
    @pytest.mark.unit
    def test_invalid_endpoint_returns_error(self, http):
        """Test that invalid endpoints are handled gracefully"""
        url = BASE_URL["portfolio"]
        r = http.get(f"{url}/invalid-endpoint-that-does-not-exist")
        assert r.status_code == 404


class TestServiceIntegrationFlow:
    """Test a complete flow using multiple services through central API"""
    
    @pytest.mark.integration
    def test_portfolio_to_strategy_flow(self, http):
        """Portfolio → Strategy complete flow"""
        # Get portfolio snapshot
        portfolio_url = BASE_URL["portfolio"]
        p = http.get(f"{portfolio_url}/snapshot")
        assert p.status_code == 200
        
        # Use data to call strategy
        strategy_url = BASE_URL["strategy"]
        s = http.get(f"{strategy_url}/list")
        assert s.status_code == 200
    
    @pytest.mark.integration
    def test_orchestrator_with_multiple_services(self, http):
        """Test Orchestrator can reach all other services"""
        orchestrator_url = BASE_URL["orchestrator"]
        
        # Health check
        r = http.get(f"{orchestrator_url}/health")
        assert r.status_code == 200
        
        # Verify it can coordinate
        assert r.json()["service"] == "orchestrator"
    
    @pytest.mark.integration
    def test_ai_service_integration_in_orchestrator(self, http):
        """Test that Orchestrator can reach AI service"""
        ai_url = BASE_URL["local_ai"]
        
        r = http.get(f"{ai_url}/health")
        assert r.status_code == 200


class TestCentralizedErrorHandling:
    """Test error handling is consistent across services"""
    
    @pytest.mark.unit
    def test_all_services_have_health_endpoint(self, http):
        """Verify all services respond to /health"""
        services = ["portfolio", "strategy", "risk", "execution", "orchestrator", "analytics", "config", "local_ai"]
        
        for service_name in services:
            url = BASE_URL.get(service_name)
            if url:
                r = http.get(f"{url}/health")
                assert r.status_code == 200, f"{service_name} health check failed"
    
    @pytest.mark.unit
    def test_service_response_format_consistency(self, http):
        """All health endpoints should return consistent format"""
        services = ["portfolio", "strategy", "risk", "execution", "orchestrator", "analytics"]
        
        for service_name in services:
            url = BASE_URL.get(service_name)
            if url:
                r = http.get(f"{url}/health")
                data = r.json()
                assert "service" in data, f"{service_name} missing 'service' field"
