"""Analytics service tests — port 3006

Covers:
  GET  /health
  GET  /trades                        — list all trade records
  GET  /strategies/metrics            — per-strategy computed metrics
  POST /strategies/metrics/refresh    — recompute metrics from trades table via pandas
  GET  /audit                         — audit log entries
  GET  /pnl/daily                     — daily PnL time series
  GET  /regimes/{pair}                — regime history for a pair

Metrics computed by /refresh:
  - total_trades, win_rate (wins / total)
  - total_pnl, avg_pnl
  - Sharpe ratio (annualised, sqrt(252) * mean/std)
  - Max drawdown percentage
"""
import pytest
from tests.shared.fixtures import BASE_URL

URL = BASE_URL["analytics"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/health").status_code == 200

    def test_service_name(self, http):
        assert http.get(f"{URL}/health").json()["service"] == "analytics"


# ---------------------------------------------------------------------------
# Trades  (GET /trades)
# ---------------------------------------------------------------------------

class TestTrades:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/trades").status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/trades").json()
        assert isinstance(body, list)

    def test_each_trade_has_required_fields_if_present(self, http):
        trades = http.get(f"{URL}/trades").json()
        if trades:
            for trade in trades[:5]:
                for field in ("id", "strategy_name", "pair", "side"):
                    assert field in trade


# ---------------------------------------------------------------------------
# Strategy metrics  (GET /strategies/metrics)
# ---------------------------------------------------------------------------

class TestStrategyMetrics:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/strategies/metrics").status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/strategies/metrics").json()
        assert isinstance(body, list)

    def test_each_metric_has_strategy_name(self, http):
        metrics = http.get(f"{URL}/strategies/metrics").json()
        for m in metrics:
            assert "strategy_name" in m

    def test_metric_fields_present_if_populated(self, http):
        metrics = http.get(f"{URL}/strategies/metrics").json()
        if metrics:
            m = metrics[0]
            for field in ("total_trades", "win_rate", "total_pnl"):
                assert field in m


# ---------------------------------------------------------------------------
# Metrics refresh  (POST /strategies/metrics/refresh)
# ---------------------------------------------------------------------------

class TestMetricsRefresh:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/strategies/metrics/refresh")
        assert r.status_code == 200

    def test_response_ok_field(self, http):
        body = http.post(f"{URL}/strategies/metrics/refresh").json()
        assert body.get("ok") is True

    def test_idempotent(self, http):
        """Running refresh twice should not error."""
        r1 = http.post(f"{URL}/strategies/metrics/refresh")
        r2 = http.post(f"{URL}/strategies/metrics/refresh")
        assert r1.status_code == 200
        assert r2.status_code == 200


# ---------------------------------------------------------------------------
# Audit log  (GET /audit)
# ---------------------------------------------------------------------------

class TestAudit:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/audit").status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/audit").json()
        assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Daily PnL  (GET /pnl/daily)
# ---------------------------------------------------------------------------

class TestDailyPnl:
    def test_returns_200(self, http):
        assert http.get(f"{URL}/pnl/daily").status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/pnl/daily").json()
        assert isinstance(body, list)


# ---------------------------------------------------------------------------
# Regimes history  (GET /regimes/{pair})
# ---------------------------------------------------------------------------

class TestRegimes:
    def test_btc_usdt_returns_200(self, http):
        r = http.get(f"{URL}/regimes/BTC_USDT")
        assert r.status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/regimes/BTC_USDT").json()
        assert isinstance(body, list)
