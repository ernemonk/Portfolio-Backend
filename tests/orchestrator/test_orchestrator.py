"""Orchestrator service tests — port 3005

Covers:
  GET  /health
  POST /classify-regime   — ADX+ATR market-regime classifier
  POST /vote              — multi-agent mock voting layer
  POST /meta-agent/evaluate — meta-agent performance review stub
  POST /pipeline/run      — full end-to-end pipeline orchestration

Regime classifier algorithm:
  - Requires >= 30 candles for a live signal; returns RANGE_BOUND (confidence 0.3) below that
  - Uses pure Python Wilder-smoothed ADX + ATR (no TA-Lib)
  - Thresholds: ADX > 25 → trending, volatility_pct > 5% → HIGH_VOLATILITY_EVENT

Pipeline flow:
  classify regime → evaluate all strategies via HTTP → mock agent vote
  → risk /approve via HTTP → execution /enqueue via HTTP
"""
import pytest
from tests.shared.fixtures import (
    BASE_URL, STRATEGY_CTX, STRATEGY_CTX_30, VOTE_BODY, INTENT_SMALL, CANDLES_3,
)

URL = BASE_URL["orchestrator"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/health").status_code == 200

    def test_service_name(self, http):
        assert http.get(f"{URL}/health").json()["service"] == "orchestrator"


# ---------------------------------------------------------------------------
# Classify regime  (POST /classify-regime?pair=...)
# ---------------------------------------------------------------------------

class TestClassifyRegime:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_response_has_required_fields(self, http):
        body = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX).json()
        for field in ("pair", "regime", "confidence", "atr", "volatility_pct"):
            assert field in body

    def test_confidence_between_0_and_1(self, http):
        body = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX).json()
        assert 0.0 <= body["confidence"] <= 1.0

    def test_regime_is_valid_enum(self, http):
        body = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX).json()
        valid_regimes = {
            "TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND",
            "HIGH_VOLATILITY_EVENT", "LOW_LIQUIDITY", "UNKNOWN",
        }
        assert body["regime"] in valid_regimes

    def test_insufficient_candles_returns_range_bound(self, http):
        """< 30 candles → classifier must return RANGE_BOUND with low confidence."""
        body = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX).json()
        # STRATEGY_CTX has 3 candles
        assert body["regime"] == "RANGE_BOUND"
        assert body["confidence"] <= 0.35

    def test_sufficient_candles_returns_non_stub_result(self, http):
        """30+ candles → ADX+ATR should produce a real classification."""
        body = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX_30).json()
        # Just verify it produced a valid regime — value depends on price data
        assert body["regime"] in {
            "TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND",
            "HIGH_VOLATILITY_EVENT", "LOW_LIQUIDITY",
        }

    def test_pair_stored_in_response(self, http):
        body = http.post(f"{URL}/classify-regime?pair=BTC%2FUSDT", json=STRATEGY_CTX).json()
        assert body["pair"] == "BTC/USDT"

    def test_missing_pair_query_param_returns_422(self, http):
        r = http.post(f"{URL}/classify-regime", json=STRATEGY_CTX)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Vote  (POST /vote)
# ---------------------------------------------------------------------------

class TestVote:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/vote", json=VOTE_BODY)
        assert r.status_code == 200

    def test_response_has_required_fields(self, http):
        body = http.post(f"{URL}/vote", json=VOTE_BODY).json()
        for field in ("action", "confidence", "votes", "threshold"):
            assert field in body

    def test_action_is_valid(self, http):
        body = http.post(f"{URL}/vote", json=VOTE_BODY).json()
        assert body["action"] in ("EXECUTE", "SKIP")

    def test_confidence_between_0_and_1(self, http):
        body = http.post(f"{URL}/vote", json=VOTE_BODY).json()
        assert 0.0 <= body["confidence"] <= 1.0

    def test_votes_is_list(self, http):
        body = http.post(f"{URL}/vote", json=VOTE_BODY).json()
        assert isinstance(body["votes"], list)

    def test_each_vote_has_agent_name_and_action(self, http):
        votes = http.post(f"{URL}/vote", json=VOTE_BODY).json()["votes"]
        for v in votes:
            assert "agent_name" in v
            assert "action" in v
            assert v["action"] in ("EXECUTE", "SKIP")


# ---------------------------------------------------------------------------
# Meta-agent  (POST /meta-agent/evaluate)
# ---------------------------------------------------------------------------

class TestMetaAgent:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/meta-agent/evaluate")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Pipeline  (POST /pipeline/run)
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/pipeline/run", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_response_has_counters(self, http):
        body = http.post(f"{URL}/pipeline/run", json=STRATEGY_CTX).json()
        for field in ("intents_generated", "approved", "rejected", "enqueued"):
            assert field in body, f"pipeline response missing: {field}"

    def test_counters_are_non_negative(self, http):
        body = http.post(f"{URL}/pipeline/run", json=STRATEGY_CTX).json()
        assert body["intents_generated"] >= 0
        assert body["approved"] >= 0
        assert body["rejected"] >= 0
        assert body["enqueued"] >= 0

    def test_no_critical_errors(self, http):
        """Pipeline should run without service-level failures."""
        body = http.post(f"{URL}/pipeline/run", json=STRATEGY_CTX).json()
        # errors list may contain "no signal" noise but not HTTP failures
        http_errors = [e for e in body.get("errors", []) if "500" in str(e) or "connection" in str(e).lower()]
        assert http_errors == [], f"Pipeline had HTTP errors: {http_errors}"
