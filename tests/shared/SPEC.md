# Test Specification — Shared Fixtures

## Purpose

This folder is not a test suite itself — it provides **shared test data** and **pytest fixtures** consumed by every other test module. It exists to ensure a single source of truth for all API payloads, so a schema change in any service only needs to be fixed in one place.

---

## Files

| File | Role |
|------|------|
| `fixtures.py` | Canonical request payloads for all 6 services |
| `conftest.py` | *(root-level)* pytest fixtures: `http`, per-service URLs, `clear_kill_switch` |

---

## What Is Defined

### `BASE_URL`
Port mapping for all microservices:

| Service | Port |
|---------|------|
| portfolio | 3001 |
| strategy | 3002 |
| risk | 3003 |
| execution | 3004 |
| orchestrator | 3005 |
| analytics | 3006 |

### OHLCV Candle Sets

| Constant | Candles | Purpose |
|----------|---------|---------|
| `CANDLES_3` | 3 | Below ADX/Sharpe threshold → regime returns RANGE_BOUND |
| `CANDLES_14` | 14 | Mid-range — enough for RSI but not ADX |
| `CANDLES_30` | 30 | Full set — ADX requires ≥ 30 candles to produce a valid signal |

Each candle is `[timestamp_ms, open, high, low, close, volume]`.

### Portfolio Snapshots

| Constant | Description |
|----------|-------------|
| `EMPTY_SNAPSHOT` | `{"balances": {}, "prices": {}}` — represents a fresh/empty portfolio |
| `SNAPSHOT_WITH_BTC` | Has `USDT: 10000`, `BTC: 0.05` at price `65000` → BTC position worth $3,250 |

### Strategy Contexts

| Constant | Candle count | Purpose |
|----------|-------------|---------|
| `STRATEGY_CTX` | 3 | Default context for unit tests that don't depend on regime quality |
| `STRATEGY_CTX_30` | 30 | Used by orchestrator regime tests needing a real ADX calculation |

Both use the `ohlcv` field (not `candles`) — this matches the `BacktestRequest` / `StrategyContext` Pydantic schema.

### Trade Intents

| Constant | Description |
|----------|-------------|
| `INTENT_SMALL` | BTC/USDT BUY, size=0.01 — well below risk limits → **should be approved** |
| `INTENT_OVERSIZED` | BTC/USDT BUY, size=10.0 — exceeds position size limit → **should be rejected** |
| `APPROVED_INTENT` | Like `INTENT_SMALL` + `risk_decision_id` field → valid `ApprovedTradeIntent` for execution |

### Composite Bodies

| Constant | Description |
|----------|-------------|
| `VOTE_BODY` | `{"intent": INTENT_SMALL, "ctx": STRATEGY_CTX}` — matches orchestrator `/vote` two-param merge |
| `BACKTEST_DCA` | DCA strategy backtest request with 30 candles and `interval_hours=1` |

---

## Design Decisions

- **`ohlcv` not `candles`** — FastAPI model uses `ohlcv` as field name in `StrategyContext`. Using `candles` causes a 422.
- **`risk_decision_id` in `APPROVED_INTENT`** — Execution service requires `ApprovedTradeIntent`; plain `TradeIntent` (without this field) returns 422.
- **`VOTE_BODY` wraps intent + ctx** — FastAPI infers two body params, so the JSON must be a dict with both keys.
- **Price in snapshot** — `SNAPSHOT_WITH_BTC` uses `prices: {"BTC/USDT": 65000}` to match the key format returned by the portfolio `/price/{pair}` route.
