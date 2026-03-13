"""Strategy service tests — port 3002

Covers:
  GET  /health
  GET  /strategies                  — list all registered strategies
  POST /strategies/{name}/enable    — enable a strategy
  POST /strategies/{name}/disable   — disable a strategy
  POST /strategies/{name}/evaluate  — run one strategy against a StrategyContext
  POST /backtest                    — event-driven backtester (BacktestRequest)
  POST /run                         — evaluate all enabled strategies
"""
import pytest
from tests.shared.fixtures import (
    BASE_URL, STRATEGY_CTX, STRATEGY_CTX_30, BACKTEST_DCA, CANDLES_3, EMPTY_SNAPSHOT,
)

URL = BASE_URL["strategy"]
KNOWN_STRATEGIES = {"dca", "grid", "momentum", "ma_crossover"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/health").status_code == 200

    def test_service_name(self, http):
        body = http.get(f"{URL}/health").json()
        assert body["service"] == "strategy"


# ---------------------------------------------------------------------------
# Strategy registry  (GET /strategies)
# ---------------------------------------------------------------------------

class TestStrategyList:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/strategies").status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/strategies").json()
        assert isinstance(body, list)

    def test_all_known_strategies_present(self, http):
        names = {s["name"] for s in http.get(f"{URL}/strategies").json()}
        assert KNOWN_STRATEGIES.issubset(names)

    def test_each_entry_has_name_and_enabled(self, http):
        for s in http.get(f"{URL}/strategies").json():
            assert "name" in s
            assert "enabled" in s


# ---------------------------------------------------------------------------
# Enable / disable  (POST /strategies/{name}/enable|disable)
# ---------------------------------------------------------------------------

class TestEnableDisable:
    def test_enable_returns_200(self, http):
        r = http.post(f"{URL}/strategies/dca/enable")
        assert r.status_code == 200

    def test_disable_returns_200(self, http):
        r = http.post(f"{URL}/strategies/dca/disable")
        assert r.status_code == 200

    def test_re_enable_after_disable(self, http):
        http.post(f"{URL}/strategies/dca/disable")
        r = http.post(f"{URL}/strategies/dca/enable")
        assert r.status_code == 200

    def test_unknown_strategy_disable_returns_404(self, http):
        r = http.post(f"{URL}/strategies/nonexistent/disable")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Evaluate  (POST /strategies/{name}/evaluate)
# ---------------------------------------------------------------------------

class TestEvaluate:
    def test_dca_returns_200(self, http):
        r = http.post(f"{URL}/strategies/dca/evaluate", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_response_has_fired_field(self, http):
        body = http.post(f"{URL}/strategies/dca/evaluate", json=STRATEGY_CTX).json()
        assert "fired" in body

    def test_response_has_signal_field(self, http):
        body = http.post(f"{URL}/strategies/dca/evaluate", json=STRATEGY_CTX).json()
        assert "signal" in body

    def test_grid_returns_200(self, http):
        r = http.post(f"{URL}/strategies/grid/evaluate", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_momentum_returns_200(self, http):
        r = http.post(f"{URL}/strategies/momentum/evaluate", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_ma_crossover_returns_200(self, http):
        r = http.post(f"{URL}/strategies/ma_crossover/evaluate", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_unknown_strategy_returns_404(self, http):
        r = http.post(f"{URL}/strategies/unknown_strat/evaluate", json=STRATEGY_CTX)
        assert r.status_code == 404

    def test_signal_shape_when_fired(self, http):
        """If a signal fires, it must contain required TradeIntent fields."""
        body = http.post(f"{URL}/strategies/dca/evaluate", json={
            **STRATEGY_CTX,
            "params": {"interval_hours": 0, "amount_usd": 100},  # 0h interval → always fires
        }).json()
        if body["fired"]:
            signal = body["signal"]
            for field in ("strategy_name", "pair", "side", "quantity"):
                assert field in signal, f"TradeIntent missing field: {field}"


# ---------------------------------------------------------------------------
# Backtest  (POST /backtest)
# ---------------------------------------------------------------------------

class TestBacktest:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/backtest", json=BACKTEST_DCA)
        assert r.status_code == 200

    def test_response_has_required_fields(self, http):
        body = http.post(f"{URL}/backtest", json=BACKTEST_DCA).json()
        for field in ("strategy_name", "pair", "total_trades", "total_pnl",
                      "win_rate", "sharpe_ratio", "max_drawdown_pct"):
            assert field in body, f"BacktestResult missing field: {field}"

    def test_win_rate_between_0_and_1(self, http):
        body = http.post(f"{URL}/backtest", json=BACKTEST_DCA).json()
        assert 0.0 <= body["win_rate"] <= 1.0

    def test_grid_backtest(self, http):
        r = http.post(f"{URL}/backtest", json={
            **BACKTEST_DCA,
            "strategy_name": "grid",
            "params": {"levels": 3, "spacing_pct": 1.0, "amount_per_level_usd": 50},
        })
        assert r.status_code == 200

    def test_momentum_backtest(self, http):
        r = http.post(f"{URL}/backtest", json={
            **BACKTEST_DCA,
            "strategy_name": "momentum",
            "params": {"rsi_period": 14, "oversold": 35, "overbought": 65, "amount_usd": 100},
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Run all  (POST /run)
# ---------------------------------------------------------------------------

class TestRunAll:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/run", json=STRATEGY_CTX)
        assert r.status_code == 200

    def test_response_has_signals_generated(self, http):
        body = http.post(f"{URL}/run", json=STRATEGY_CTX).json()
        assert "signals_generated" in body

    def test_signals_generated_is_int(self, http):
        body = http.post(f"{URL}/run", json=STRATEGY_CTX).json()
        assert isinstance(body["signals_generated"], int)
