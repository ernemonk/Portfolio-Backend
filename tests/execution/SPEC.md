# Test Specification — Execution Service

**Service:** `execution`  
**Port:** `3004`  
**File:** `test_execution.py`

---

## What This Service Does

The execution service is the **final stage** of the trading pipeline. It receives approved trade intents (already validated by the risk service) and:

- Validates the intent has a `risk_decision_id` (proof of risk approval)
- Enqueues the order into Redis
- Executes the trade in **paper mode** (simulated) — no real exchange calls
- Returns a receipt with order ID, timestamp, and fill details

The service will reject any plain `TradeIntent` that hasn't been approved by risk.

---

## Endpoints Tested

| Method | Path | What we test |
|--------|------|-------------|
| `GET` | `/health` | Service alive |
| `POST` | `/enqueue` | Accepts an `ApprovedTradeIntent` and queues it |
| `GET` | `/queue/depth` | Returns the number of orders currently in the Redis queue |

---

## Test Classes

### `TestHealth`
- Returns 200 with `"service": "execution"`

### `TestEnqueue`
- `APPROVED_INTENT` (has `risk_decision_id`) → 200 or 201
- Response has `status` field equal to `"queued"` or `"accepted"`
- Response has `is_paper: true` (confirms paper trading mode)
- Response has `order_id` field
- Plain `TradeIntent` without `risk_decision_id` → **422 Unprocessable Entity** (Pydantic validation fails)
- Multiple sequential enqueue calls all succeed

### `TestQueueDepth`
- GET `/queue/depth` returns 200
- Response has `"depth"` field
- `depth` is a non-negative integer
- After enqueuing, depth is ≥ 1

---

## Key Assertions

- **`risk_decision_id` required:** `ApprovedTradeIntent` extends `TradeIntent` by adding this required field. Sending a plain `TradeIntent` causes a Pydantic 422 because the field is missing.
- **Paper mode always on:** This system is in paper-trading mode. `is_paper: true` must always be present in enqueue receipts.
- **Queue depth monotonicity:** After N successful enqueues, `depth >= N` (queue may have prior entries from other tests).

---

## Schema: `ApprovedTradeIntent`

```json
{
  "pair": "BTC/USDT",
  "side": "BUY",
  "size": 0.01,
  "price": 65000.0,
  "strategy_name": "dca",
  "risk_decision_id": "test-decision-001"
}
```

The `risk_decision_id` field distinguishes this from a bare `TradeIntent`.

---

## Dependencies

- Redis must be running (execution writes orders to a Redis list/stream)
- Risk service does NOT need to be running for execution unit tests (the `risk_decision_id` is already embedded in the intent)
