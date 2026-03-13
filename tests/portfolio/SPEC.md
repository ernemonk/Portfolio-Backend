# Test Specification — Portfolio Service

**Service:** `portfolio`  
**Port:** `3001`  
**File:** `test_portfolio.py`

---

## What This Service Does

The portfolio service is responsible for:
- Maintaining a real-time snapshot of the user's portfolio (balances + prices) in **Redis**
- Fetching live prices from **CoinGecko** via a background sync worker
- Exposing a REST API to read/write the snapshot and query positions + PnL

---

## Endpoints Tested

| Method | Path | What we test |
|--------|------|-------------|
| `GET` | `/health` | Service is alive and identifies itself |
| `POST` | `/sync` | Triggers CoinGecko price fetch and Redis write |
| `GET` | `/snapshot` | Returns current portfolio snapshot |
| `POST` | `/snapshot` | Upserts a new snapshot (used by other services in tests) |
| `GET` | `/positions` | Returns per-asset position list |
| `GET` | `/pnl` | Returns profit/loss summary |
| `GET` | `/price/{pair}` | Returns the current price for a single trading pair |

---

## Test Classes

### `TestHealth`
- Confirms the service responds with HTTP 200
- Confirms the JSON body contains `"service": "portfolio"`

### `TestSync`
- POST `/sync` returns 200
- Response contains an `"ok": true` field
- Sync is idempotent — calling it twice doesn't error

### `TestGetSnapshot`
- GET `/snapshot` returns 200
- Response is a dict (not a list)
- Response has a `"balances"` key
- Response has a `"prices"` key

### `TestPostSnapshot`
- POST `/snapshot` with `EMPTY_SNAPSHOT` returns 200
- POST `/snapshot` with `SNAPSHOT_WITH_BTC` returns 200
- After upserting `SNAPSHOT_WITH_BTC`, GET `/snapshot` reflects the new balances *(restores original after)*

### `TestPositions`
- GET `/positions` returns a list
- Each position item has `pair`, `quantity`, `value_usd` fields
- Allocation percentages across all positions sum to ~100%

### `TestPnl`
- GET `/pnl` returns 200
- Response has `"total_value_usd"` field
- Response has `"pnl_pct"` field

### `TestPriceFeed`
- GET `/price/BTC%2FUSDT` returns 200
- Price is a positive float
- GET `/price/UNKNOWN%2FUSD` returns 404

---

## Key Assertions

- Allocation sum: `abs(sum(alloc_pcts) - 100) < 1.0` — allows rounding
- Snapshot round-trip: write `SNAPSHOT_WITH_BTC`, read back, assert `"BTC" in balances`
- Price positivity: `price > 0`

---

## Dependencies

- Redis must be running and accessible from the portfolio container
- CoinGecko API must be reachable (for `/sync`); tests are designed to pass even with cached prices
