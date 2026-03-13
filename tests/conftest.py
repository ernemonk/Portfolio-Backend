"""
pytest conftest — project-wide.

Provides:
  • `client` — a synchronous httpx client pre-configured with the correct base
    URL for each service under test (injected via the `base_url` fixture param)
  • `async_client` — async variant for tests that use anyio
  • `service_urls` — dict of all base URLs for multi-service tests
"""
import pytest
import httpx

from tests.shared.fixtures import BASE_URL


# ---------------------------------------------------------------------------
# Sync client (default — most tests use this)
# ---------------------------------------------------------------------------

@pytest.fixture
def http():
    """Plain requests-style httpx client with a 10s timeout."""
    with httpx.Client(timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# Per-service URL fixtures (convenience shortcuts)
# ---------------------------------------------------------------------------

@pytest.fixture
def portfolio_url():
    return BASE_URL["portfolio"]

@pytest.fixture
def strategy_url():
    return BASE_URL["strategy"]

@pytest.fixture
def risk_url():
    return BASE_URL["risk"]

@pytest.fixture
def execution_url():
    return BASE_URL["execution"]

@pytest.fixture
def orchestrator_url():
    return BASE_URL["orchestrator"]

@pytest.fixture
def analytics_url():
    return BASE_URL["analytics"]


# ---------------------------------------------------------------------------
# Autouse: ensure kill-switch is OFF before every test in the risk suite
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def clear_kill_switch(http, risk_url):
    """Ensure kill-switch is cleared before and after each test that uses it."""
    http.delete(f"{risk_url}/kill-switch")
    yield
    http.delete(f"{risk_url}/kill-switch")
