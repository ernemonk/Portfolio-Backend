"""Portfolio service tests — port 3001

Covers:
  GET  /health
  POST /sync       — trigger CoinGecko price fetch & cache snapshot
  GET  /snapshot   — read cached PortfolioSnapshot from Redis
  POST /snapshot   — upsert a custom snapshot
  GET  /positions  — positions array from cached snapshot
  GET  /pnl        — daily/weekly PnL from cached snapshot
  GET  /price/{pair} — live price lookup (CoinGecko, 5-min cache)
"""
import pytest
from tests.shared.fixtures import BASE_URL, EMPTY_SNAPSHOT


URL = BASE_URL["portfolio"]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, http):
        r = http.get(f"{URL}/health")
        assert r.status_code == 200

    def test_service_name(self, http):
        body = http.get(f"{URL}/health").json()
        assert body["service"] == "portfolio"

    def test_redis_check_ok(self, http):
        body = http.get(f"{URL}/health").json()
        assert body["checks"]["redis"] == "ok"

    def test_snapshot_check_present(self, http):
        body = http.get(f"{URL}/health").json()
        # After startup sync, snapshot must exist
        assert body["checks"]["snapshot"] == "ok"


# ---------------------------------------------------------------------------
# Sync  (POST /sync)
# ---------------------------------------------------------------------------

class TestSync:
    def test_returns_200(self, http):
        r = http.post(f"{URL}/sync")
        assert r.status_code == 200

    def test_response_shape(self, http):
        body = http.post(f"{URL}/sync").json()
        assert "ok" in body
        assert body["ok"] is True
        assert "total_value_usd" in body
        assert "positions" in body

    def test_total_value_positive(self, http):
        body = http.post(f"{URL}/sync").json()
        assert body["total_value_usd"] > 0

    def test_positions_count(self, http):
        body = http.post(f"{URL}/sync").json()
        # Paper account has 4 positions (BTC, ETH, SOL, USDT)
        assert body["positions"] == 4


# ---------------------------------------------------------------------------
# Snapshot GET  (/snapshot)
# ---------------------------------------------------------------------------

class TestGetSnapshot:
    def test_returns_200(self, http):
        r = http.get(f"{URL}/snapshot")
        assert r.status_code == 200

    def test_required_fields(self, http):
        body = http.get(f"{URL}/snapshot").json()
        for field in ("total_value_usd", "daily_pnl", "daily_pnl_pct",
                      "weekly_pnl", "positions", "portfolio_heat_pct"):
            assert field in body, f"missing field: {field}"

    def test_total_value_positive(self, http):
        body = http.get(f"{URL}/snapshot").json()
        assert body["total_value_usd"] > 0

    def test_positions_is_list(self, http):
        body = http.get(f"{URL}/snapshot").json()
        assert isinstance(body["positions"], list)

    def test_each_position_has_required_fields(self, http):
        body = http.get(f"{URL}/snapshot").json()
        for pos in body["positions"]:
            for field in ("asset", "quantity", "value_usd", "allocation_pct"):
                assert field in pos

    def test_allocation_pcts_sum_to_100(self, http):
        body = http.get(f"{URL}/snapshot").json()
        total_alloc = sum(p["allocation_pct"] for p in body["positions"])
        assert abs(total_alloc - 100.0) < 1.0  # allow rounding


# ---------------------------------------------------------------------------
# Snapshot POST  (/snapshot upsert)
# ---------------------------------------------------------------------------

class TestPostSnapshot:
    def test_upsert_returns_200(self, http):
        r = http.post(f"{URL}/snapshot", json=EMPTY_SNAPSHOT)
        assert r.status_code == 200

    def test_upsert_ok_flag(self, http):
        body = http.post(f"{URL}/snapshot", json=EMPTY_SNAPSHOT).json()
        assert body.get("ok") is True

    def test_upserted_snapshot_is_readable(self, http):
        custom = {**EMPTY_SNAPSHOT, "total_value_usd": 99999.0}
        http.post(f"{URL}/snapshot", json=custom)
        snap = http.get(f"{URL}/snapshot").json()
        assert snap["total_value_usd"] == 99999.0

    def test_restore_live_snapshot(self, http):
        # Put back a real sync so other tests aren't broken by the custom value
        http.post(f"{URL}/sync")


# ---------------------------------------------------------------------------
# Positions  (GET /positions)
# ---------------------------------------------------------------------------

class TestPositions:
    def test_returns_200(self, http):
        r = http.get(f"{URL}/positions")
        assert r.status_code == 200

    def test_returns_list(self, http):
        body = http.get(f"{URL}/positions").json()
        assert isinstance(body, list)

    def test_positions_not_empty(self, http):
        body = http.get(f"{URL}/positions").json()
        assert len(body) > 0


# ---------------------------------------------------------------------------
# PnL  (GET /pnl)
# ---------------------------------------------------------------------------

class TestPnl:
    def test_returns_200(self, http):
        r = http.get(f"{URL}/pnl")
        assert r.status_code == 200

    def test_has_daily_and_weekly(self, http):
        body = http.get(f"{URL}/pnl").json()
        assert "daily" in body
        assert "weekly" in body

    def test_values_are_numeric(self, http):
        body = http.get(f"{URL}/pnl").json()
        assert isinstance(body["daily"], (int, float))
        assert isinstance(body["weekly"], (int, float))


# ---------------------------------------------------------------------------
# Price feed  (GET /price/{pair})
# ---------------------------------------------------------------------------

class TestPriceFeed:
    def test_btc_usdt_returns_200(self, http):
        r = http.get(f"{URL}/price/BTC/USDT")
        assert r.status_code == 200

    def test_btc_price_positive(self, http):
        body = http.get(f"{URL}/price/BTC/USDT").json()
        assert body["price_usd"] > 0

    def test_response_contains_pair(self, http):
        body = http.get(f"{URL}/price/BTC/USDT").json()
        assert body["pair"] == "BTC/USDT"

    def test_eth_usdt_returns_200(self, http):
        r = http.get(f"{URL}/price/ETH/USDT")
        assert r.status_code == 200

    def test_unknown_pair_returns_404(self, http):
        r = http.get(f"{URL}/price/UNKNOWN/USDT")
        assert r.status_code == 404
