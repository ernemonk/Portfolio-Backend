"""Integration tests — full cross-service pipeline

Marks: @pytest.mark.integration  (excluded from default `pytest` run;
                                   run explicitly with `pytest -m integration`)

These tests prove that the microservices talk to each other correctly over
the Docker network (via localhost ports) and that data flows through the
system end-to-end.

Pipeline under test:
  1. Portfolio /sync    → populate Redis price snapshot
  2. Risk /evaluate     → TradeIntent → RiskDecision (fetches snapshot from Redis)
  3. Risk /approve      → RiskDecision → ApprovedTradeIntent (with risk_decision_id)
  4. Execution /enqueue → ApprovedTradeIntent → paper order receipt

Each step is also validated in isolation to confirm the component contract
before asserting the full chain.
"""
import pytest
from tests.shared.fixtures import (
    BASE_URL, INTENT_SMALL, APPROVED_INTENT,
)

PORTFOLIO_URL = BASE_URL["portfolio"]
RISK_URL      = BASE_URL["risk"]
EXECUTION_URL = BASE_URL["execution"]
ORCHESTRATOR_URL = BASE_URL["orchestrator"]


# ---------------------------------------------------------------------------
# Full pipeline chain
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPortfolioToRiskToExecution:
    """Trade intent flows from risk evaluation all the way to execution queue."""

    def test_risk_evaluate_accepts_small_intent(self, http):
        r = http.post(f"{RISK_URL}/evaluate", json=INTENT_SMALL)
        assert r.status_code == 200
        assert r.json()["approved"] is True

    def test_approved_intent_can_be_enqueued(self, http, clear_kill_switch):
        r = http.post(f"{EXECUTION_URL}/enqueue", json=APPROVED_INTENT)
        assert r.status_code in (200, 201)
        body = r.json()
        # Paper mode returns OrderResult with filled/placed; live mode returns placed
        assert body.get("status") in ("queued", "accepted", "filled", "placed", "partial")

    def test_full_portfolio_to_execution_chain(self, http, clear_kill_switch):
        """
        Step 1: sync portfolio prices into Redis.
        Step 2: risk-evaluate a small BTC/USDT trade.
        Step 3: approve the risk decision.
        Step 4: enqueue the approved intent.
        """
        # Step 1 — sync
        sync_r = http.post(f"{PORTFOLIO_URL}/sync")
        assert sync_r.status_code == 200

        # Step 2 — risk evaluate (uses TradeIntent; risk fetches snapshot from Redis)
        risk_r = http.post(f"{RISK_URL}/evaluate", json=INTENT_SMALL)
        assert risk_r.status_code == 200
        risk_body = risk_r.json()
        assert risk_body["approved"] is True, f"Risk rejected: {risk_body}"

        # Step 3 — approve (enrich intent with risk_decision_id)
        decision_id = risk_body.get("decision_id") or risk_body.get("id", "test-id")
        approved_intent = {**INTENT_SMALL, "risk_decision_id": decision_id}
        approve_r = http.post(f"{RISK_URL}/approve", json=approved_intent)
        assert approve_r.status_code == 200

        # Step 4 — enqueue
        enqueue_r = http.post(f"{EXECUTION_URL}/enqueue", json=approved_intent)
        assert enqueue_r.status_code in (200, 201)
        enqueue_body = enqueue_r.json()
        assert enqueue_body["status"] in ("queued", "accepted", "filled", "placed")
        assert enqueue_body.get("is_paper") is True


# ---------------------------------------------------------------------------
# Orchestrator pipeline integration
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestOrchestratorPipeline:
    """
    Orchestrator /pipeline/run drives the full internal flow:
    classify regime → evaluate strategies → vote → risk approve → enqueue
    It should return counters and not crash even if no strategies fire.
    """
    from tests.shared.fixtures import STRATEGY_CTX

    def test_pipeline_returns_valid_response(self, http, clear_kill_switch):
        from tests.shared.fixtures import STRATEGY_CTX
        r = http.post(f"{ORCHESTRATOR_URL}/pipeline/run", json=STRATEGY_CTX)
        assert r.status_code == 200
        body = r.json()
        assert "intents_generated" in body
        assert "enqueued" in body

    def test_pipeline_enqueued_lte_intents_generated(self, http, clear_kill_switch):
        """Can't enqueue more orders than were generated."""
        from tests.shared.fixtures import STRATEGY_CTX
        body = http.post(f"{ORCHESTRATOR_URL}/pipeline/run", json=STRATEGY_CTX).json()
        assert body["enqueued"] <= body["intents_generated"]

    def test_pipeline_approved_lte_intents_generated(self, http, clear_kill_switch):
        from tests.shared.fixtures import STRATEGY_CTX
        body = http.post(f"{ORCHESTRATOR_URL}/pipeline/run", json=STRATEGY_CTX).json()
        assert body["approved"] <= body["intents_generated"]


# ---------------------------------------------------------------------------
# Kill-switch propagation
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestKillSwitchPropagation:
    """When risk kill-switch is active, execution should reject new orders
    (risk will reject at /evaluate before they reach execution)."""

    def test_kill_switch_blocks_risk_evaluation(self, http, clear_kill_switch):
        # Arm kill-switch
        arm_r = http.post(
            f"{RISK_URL}/kill-switch",
            json={"reason": "integration test", "level": 6},
        )
        assert arm_r.status_code == 200

        # Risk evaluation should now reject
        eval_r = http.post(f"{RISK_URL}/evaluate", json=INTENT_SMALL)
        assert eval_r.status_code == 200
        assert eval_r.json()["approved"] is False
        assert eval_r.json().get("rejection_reason") == "KILL_SWITCH"

        # clear_kill_switch fixture will disarm after test
