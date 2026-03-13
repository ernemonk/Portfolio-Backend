# Test Specification — Risk Service

**Service:** `risk`  
**Port:** `3003`  
**File:** `test_risk.py`

---

## What This Service Does

The risk service is the **gatekeeper** of the trading pipeline. Every trade intent must pass through risk evaluation before it can be sent to execution. The service enforces:

- **Position size limits** (L1 check) — max 0.5 BTC or $500 per trade
- **Concentration limits** (L2 check) — max 20% of portfolio in one asset
- **Drawdown circuit-breaker** (L3 check) — pauses if portfolio drops > 10%
- **Correlation guards** (L4 check) — prevents over-exposure to correlated pairs
- **Volatility guards** (L5 check) — reduces size in high-ATR markets
- **Kill-switch** (L6 check) — manual emergency stop; blocks ALL trades

The service fetches the portfolio snapshot from Redis internally — callers do NOT pass snapshot data.

---

## Endpoints Tested

| Method | Path | What we test |
|--------|------|-------------|
| `GET` | `/health` | Service alive |
| `GET` | `/config` | Returns current risk config (limits) |
| `PUT` | `/config` | Updates a risk limit at runtime |
| `POST` | `/evaluate` | Evaluates a `TradeIntent` through all L1–L6 checks |
| `POST` | `/approve` | Converts an evaluated intent into `ApprovedTradeIntent` |
| `POST` | `/kill-switch` | Arms the emergency stop |
| `DELETE` | `/kill-switch` | Disarms the emergency stop |

---

## Test Classes

### `TestHealth`
- Returns 200 with `"service": "risk"`

### `TestConfig`
- GET `/config` returns a dict
- Config has `max_position_size_usd` field
- PUT `/config` can update a limit at runtime

### `TestEvaluate`
- `INTENT_SMALL` (0.01 BTC, ~$650 notional) → `approved: true`
- `INTENT_OVERSIZED` (10 BTC, ~$650,000 notional) → `approved: false`, `rejection_reason: "POSITION_SIZE_EXCEEDED"`
- Each evaluation returns `decision_id` field (UUID for traceability)
- Kill-switch blocks ALL trades → `rejection_reason: "KILL_SWITCH"`

### `TestApprove`
- POST `/approve` with `APPROVED_INTENT` returns 200
- Response contains `risk_decision_id` matching what was passed

### `TestKillSwitch`
- POST `/kill-switch` with `level: 6` returns 200
- After arming: evaluate any intent → `approved: false`, `rejection_reason: "KILL_SWITCH"`
- Kill-switch response includes `"level": 6`
- DELETE `/kill-switch` returns 200
- After disarm: a small trade is approved again (L1 passes)

---

## Key Assertions

- **L1 threshold:** `max_position_size_usd` default is 500. `INTENT_OVERSIZED` at 10 BTC × $65,000 = $650,000 → clearly over.
- **Kill-switch level:** Level 6 is the highest — blocks all further evaluation.
- **No snapshot in request:** Risk fetches snapshot from Redis by itself. Passing `snapshot` in the request body causes a 422 (unexpected field).
- **`clear_kill_switch` fixture:** Used as autouse in kill-switch tests to guarantee state cleanup between tests.

---

## Test Isolation

The `clear_kill_switch` fixture is declared in `conftest.py` and calls `DELETE /kill-switch` both before and after the test to ensure:
- Tests don't fail because a previous test left the kill-switch armed
- Tests don't leave the kill-switch armed for subsequent tests

---

## Dependencies

- Redis must be running (risk reads portfolio snapshot from it)
- Portfolio service does NOT need to be running for basic L1 tests (snapshot can be absent/empty; L1 only checks notional size)
