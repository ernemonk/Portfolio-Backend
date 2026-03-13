# Test Specification — Analytics Service

**Service:** `analytics`  
**Port:** `3006`  
**File:** `test_analytics.py`

---

## What This Service Does

The analytics service is the **reporting layer** of the system. It reads trade records and regime classifications from persistent storage (SQLite/Firestore) and computes:

- **Per-strategy performance metrics** — win rate, total PnL, Sharpe ratio, max drawdown
- **Daily PnL time series** — for charting equity curves
- **Audit log** — all system events (pipeline runs, risk decisions, kill-switch events)
- **Regime history** — historical regime classifications per trading pair

Metrics are recomputed on demand via `POST /strategies/metrics/refresh` which runs a pandas groupby pipeline over all trade records.

---

## Endpoints Tested

| Method | Path | What we test |
|--------|------|-------------|
| `GET` | `/health` | Service alive |
| `GET` | `/trades` | All trade records |
| `GET` | `/strategies/metrics` | Per-strategy computed metrics |
| `POST` | `/strategies/metrics/refresh` | Recompute metrics from trades table |
| `GET` | `/audit` | Audit log entries |
| `GET` | `/pnl/daily` | Daily PnL time series |
| `GET` | `/regimes/{pair}` | Regime classification history for a pair |

---

## Test Classes

### `TestHealth`
- Returns 200 with `"service": "analytics"`

### `TestTrades`
- GET `/trades` returns 200
- Response is a list (may be empty in a fresh environment)
- If trades exist, each has `id`, `strategy_name`, `pair`, `side` fields

### `TestStrategyMetrics`
- GET `/strategies/metrics` returns 200
- Response is a list
- Each item has `strategy_name`
- If metrics are populated, each item has `total_trades`, `win_rate`, `total_pnl`

### `TestMetricsRefresh`
- POST `/strategies/metrics/refresh` returns 200
- Response has `"ok": true`
- Calling refresh twice in a row is idempotent (no error)

### `TestAudit`
- GET `/audit` returns 200
- Response is a list

### `TestDailyPnl`
- GET `/pnl/daily` returns 200
- Response is a list

### `TestRegimes`
- GET `/regimes/BTC_USDT` returns 200
- Response is a list

---

## Key Assertions

- **Empty is valid:** All list endpoints accept an empty list `[]` — tests don't fail on empty data, they only assert shape when data exists.
- **Metrics refresh idempotency:** The refresh endpoint re-runs the full pandas groupby. Running it twice must not error (e.g., no duplicate-key issues).
- **Pair format in URL:** Regime history uses `BTC_USDT` (underscore) in the path, not `BTC/USDT` (slash would break URL routing).

---

## Metrics Computed by Refresh

The `/strategies/metrics/refresh` endpoint recomputes for each `strategy_name`:

| Metric | Formula |
|--------|---------|
| `total_trades` | `COUNT(*)` |
| `win_rate` | `COUNT(pnl > 0) / total_trades` |
| `total_pnl` | `SUM(pnl)` |
| `avg_pnl` | `MEAN(pnl)` |
| `sharpe_ratio` | `sqrt(252) × mean(pnl) / std(pnl)` (annualised) |
| `max_drawdown_pct` | Max peak-to-trough drawdown as a percentage |

---

## Dependencies

- SQLite or Firestore must be accessible to read trade records
- No Redis dependency (analytics is read-only from the message store)
- Metrics refresh may return empty metrics if no trades have been recorded yet
