"""Execution service tests — port 3004

Covers:
  GET  /health
  POST /enqueue     — accept an ApprovedTradeIntent, return OrderResult
  GET  /queue/depth — current depth of the execution queue

Contract:
  - Execution service only accepts ApprovedTradeIntent (has risk_decision_id).
  - In PAPER_MODE the order is simulated; no live exchange call is made.
  - In live mode the ccxt connector is used (EXCHANGE_ID env var).
  - Queue depth tracks pending intents; should be 0 after each order in paper.
"""
import pytest
from tests.shared.fixtures import BASE_URL, APPROVED_INTENT, INTENT_SMALL

URL = BASE_URL["execution"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/health").status_code == 200

    def test_service_name(self, http):
        assert http.get(f"{URL}/health").json()["service"] == "execution"


# ---------------------------------------------------------------------------
# Enqueue  (POST /enqueue)
# ---------------------------------------------------------------------------

class TestEnqueue:
    def test_approved_intent_accepted(self, http):
        """ApprovedTradeIntent (has risk_decision_id) must return 200."""
        r = http.post(f"{URL}/enqueue", json=APPROVED_INTENT)
        assert r.status_code == 200

    def test_response_shape(self, http):
        body = http.post(f"{URL}/enqueue", json=APPROVED_INTENT).json()
        # OrderResult fields
        assert "order_id" in body
        assert "status" in body

    def test_order_id_is_string(self, http):
        body = http.post(f"{URL}/enqueue", json=APPROVED_INTENT).json()
        assert isinstance(body["order_id"], str)
        assert len(body["order_id"]) > 0

    def test_paper_order_status(self, http):
        body = http.post(f"{URL}/enqueue", json=APPROVED_INTENT).json()
        assert body["status"] in ("placed", "filled", "partial", "failed")

    def test_paper_flag_set(self, http):
        body = http.post(f"{URL}/enqueue", json=APPROVED_INTENT).json()
        assert body.get("is_paper") is True

    def test_unapproved_intent_rejected(self, http):
        """Plain TradeIntent without risk_decision_id must be rejected (422)."""
        r = http.post(f"{URL}/enqueue", json=INTENT_SMALL)
        assert r.status_code == 422

    def test_multiple_orders_accepted(self, http):
        for i in range(3):
            unique_intent = {**APPROVED_INTENT, "risk_decision_id": f"test-{i}"}
            r = http.post(f"{URL}/enqueue", json=unique_intent)
            assert r.status_code == 200


# ---------------------------------------------------------------------------
# Queue depth  (GET /queue/depth)
# ---------------------------------------------------------------------------

class TestQueueDepth:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/queue/depth").status_code == 200

    def test_depth_is_non_negative(self, http):
        body = http.get(f"{URL}/queue/depth").json()
        # Response may be {"depth": N} or just a number
        depth = body.get("depth", body) if isinstance(body, dict) else body
        assert depth >= 0
