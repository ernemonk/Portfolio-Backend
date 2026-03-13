"""Risk engine tests — port 3003

Covers:
  GET    /health
  GET    /config           — read RiskConfig
  PUT    /config           — update RiskConfig
  POST   /evaluate         — run TradeIntent through L1–L6 capital protection
  POST   /approve          — convert approved TradeIntent → ApprovedTradeIntent
  POST   /kill-switch      — activate emergency stop
  DELETE /kill-switch      — clear emergency stop

Risk Level hierarchy:
  L6  Kill-switch         — checked first, hard stop, no further checks
  L1  Position size       — trade value must be <= max_position_size_pct of portfolio
  L2  Strategy allocation — strategy's total allocation <= max_strategy_allocation_pct
  L3  Portfolio heat      — total open risk <= max_portfolio_heat_pct
  L4  Daily loss limit    — realised daily loss < daily_loss_limit_usd
  L5  Weekly drawdown     — weekly drawdown % < weekly_drawdown_pct
"""
import pytest
from tests.shared.fixtures import (
    BASE_URL, INTENT_SMALL, INTENT_OVERSIZED, EMPTY_SNAPSHOT,
)

URL = BASE_URL["risk"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/health").status_code == 200

    def test_service_name(self, http):
        assert http.get(f"{URL}/health").json()["service"] == "risk"


# ---------------------------------------------------------------------------
# Config  (GET /config, PUT /config)
# ---------------------------------------------------------------------------

class TestConfig:
    def test_get_config_returns_200(self, http):
        assert http.get(f"{URL}/config").status_code == 200

    def test_config_has_required_fields(self, http):
        body = http.get(f"{URL}/config").json()
        for field in ("max_position_size_pct", "max_strategy_allocation_pct",
                      "max_portfolio_heat_pct", "daily_loss_limit_usd",
                      "weekly_drawdown_pct", "max_leverage"):
            assert field in body

    def test_put_config_returns_200(self, http):
        cfg = http.get(f"{URL}/config").json()
        r = http.put(f"{URL}/config", json=cfg)
        assert r.status_code == 200

    def test_updated_config_is_reflected(self, http):
        original = http.get(f"{URL}/config").json()
        http.put(f"{URL}/config", json={**original, "max_leverage": 2.0})
        updated = http.get(f"{URL}/config").json()
        assert updated["max_leverage"] == 2.0
        # Restore
        http.put(f"{URL}/config", json=original)


# ---------------------------------------------------------------------------
# Evaluate  (POST /evaluate)
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_small_trade_approved(self, http, clear_kill_switch):
        """0.01 BTC @ $30k = 3% of $10k portfolio — should pass all levels."""
        body = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()
        assert body["approved"] is True

    def test_response_has_required_fields(self, http):
        body = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()
        for field in ("id", "approved", "checks_performed", "trade_intent_id"):
            assert field in body

    def test_checks_performed_is_list(self, http):
        body = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()
        assert isinstance(body["checks_performed"], list)

    def test_checks_performed_not_empty(self, http):
        body = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()
        assert len(body["checks_performed"]) > 0

    def test_each_check_has_required_fields(self, http):
        checks = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()["checks_performed"]
        for check in checks:
            for field in ("name", "level", "passed", "value", "limit"):
                assert field in check, f"RiskCheck missing field: {field}"

    # -- L1: position size -------------------------------------------------

    def test_l1_oversized_trade_rejected(self, http, clear_kill_switch):
        """10 BTC @ $30k = $300k = 3000% of $10k portfolio — must fail L1."""
        body = http.post(f"{URL}/evaluate", json=INTENT_OVERSIZED).json()
        assert body["approved"] is False

    def test_l1_rejection_reason(self, http, clear_kill_switch):
        body = http.post(f"{URL}/evaluate", json=INTENT_OVERSIZED).json()
        assert body["rejection_reason"] == "POSITION_SIZE_EXCEEDED"

    def test_l1_is_level_1(self, http, clear_kill_switch):
        checks = http.post(f"{URL}/evaluate", json=INTENT_OVERSIZED).json()["checks_performed"]
        l1 = next((c for c in checks if c["level"] == 1), None)
        assert l1 is not None
        assert l1["passed"] is False

    # -- L6: kill-switch ---------------------------------------------------

    def test_kill_switch_blocks_trade(self, http):
        http.post(f"{URL}/kill-switch")
        try:
            body = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()
            assert body["approved"] is False
            assert body["rejection_reason"] == "KILL_SWITCH"
        finally:
            http.delete(f"{URL}/kill-switch")

    def test_kill_switch_is_level_6(self, http):
        http.post(f"{URL}/kill-switch")
        try:
            checks = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()["checks_performed"]
            l6 = next((c for c in checks if c["level"] == 6), None)
            assert l6 is not None
            assert l6["passed"] is False
        finally:
            http.delete(f"{URL}/kill-switch")

    def test_after_clear_kill_switch_trade_can_pass(self, http):
        http.post(f"{URL}/kill-switch")
        http.delete(f"{URL}/kill-switch")
        body = http.post(f"{URL}/evaluate", json=INTENT_SMALL).json()
        assert body["approved"] is True


# ---------------------------------------------------------------------------
# Approve  (POST /approve)
# ---------------------------------------------------------------------------

class TestApprove:
    def test_returns_200(self, http, clear_kill_switch):
        r = http.post(f"{URL}/approve", json=INTENT_SMALL)
        assert r.status_code == 200

    def test_response_has_risk_decision_id(self, http, clear_kill_switch):
        body = http.post(f"{URL}/approve", json=INTENT_SMALL).json()
        assert "risk_decision_id" in body

    def test_approved_intent_inherits_trade_fields(self, http, clear_kill_switch):
        body = http.post(f"{URL}/approve", json=INTENT_SMALL).json()
        assert body["pair"] == INTENT_SMALL["pair"]
        assert body["side"] == INTENT_SMALL["side"]


# ---------------------------------------------------------------------------
# Kill-switch  (POST / DELETE /kill-switch)
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_activate_returns_200(self, http):
        r = http.post(f"{URL}/kill-switch")
        assert r.status_code == 200
        http.delete(f"{URL}/kill-switch")

    def test_clear_returns_200(self, http):
        http.post(f"{URL}/kill-switch")
        r = http.delete(f"{URL}/kill-switch")
        assert r.status_code == 200

    def test_activate_idempotent(self, http):
        http.post(f"{URL}/kill-switch")
        r = http.post(f"{URL}/kill-switch")
        assert r.status_code == 200
        http.delete(f"{URL}/kill-switch")
