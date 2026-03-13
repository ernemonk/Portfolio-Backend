# Test Specification — Orchestrator Service

**Service:** `orchestrator`  
**Port:** `3005`  
**File:** `test_orchestrator.py`

---

## What This Service Does

The orchestrator is the **brain** of the system. It ties all other services together by:

1. **Classifying the current market regime** using ADX + ATR (pure Python, no TA-Lib)
2. **Evaluating all trading strategies** by calling the strategy service
3. **Routing signals through a multi-agent voting layer** to filter low-confidence trades
4. **Submitting approved intents to risk** and forwarding approvals to execution
5. **Running a meta-agent** that monitors strategy performance over time

The full flow is exposed as `POST /pipeline/run` which executes all steps atomically.

---

## Endpoints Tested

| Method | Path | What we test |
|--------|------|-------------|
| `GET` | `/health` | Service alive |
| `POST` | `/classify-regime` | ADX/ATR regime classifier |
| `POST` | `/vote` | Multi-agent voting on a trade intent |
| `POST` | `/meta-agent/evaluate` | Meta-agent performance stub |
| `POST` | `/pipeline/run` | Full end-to-end pipeline in one call |

---

## Test Classes

### `TestHealth`
- Returns 200 with `"service": "orchestrator"`

### `TestClassifyRegime`

**Route:** `POST /classify-regime?pair=BTC%2FUSDT` with `StrategyContext` body

- Returns 200
- Response has `pair`, `regime`, `confidence`, `atr`, `volatility_pct`
- `confidence` is between 0.0 and 1.0
- `regime` is one of: `TRENDING_UP`, `TRENDING_DOWN`, `RANGE_BOUND`, `HIGH_VOLATILITY_EVENT`, `LOW_LIQUIDITY`, `UNKNOWN`
- **< 30 candles → `RANGE_BOUND` with confidence ≤ 0.35** (fallback path, insufficient data)
- **≥ 30 candles → produces a real ADX-derived regime**
- `pair` in response matches the query param
- Missing `?pair=` query param → **422**

**Why this threshold matters:**  
ADX requires at least `(2 × period) + 1` candles to produce a meaningful value. The service uses period=14, so 29 candles minimum. The code treats < 30 as "insufficient data" and returns the RANGE_BOUND stub.

### `TestVote`

**Route:** `POST /vote` with `{"intent": TradeIntent, "ctx": StrategyContext}`

- Returns 200
- Response has `action`, `confidence`, `votes`, `threshold`
- `action` is `"EXECUTE"` or `"SKIP"`
- `confidence` is between 0.0 and 1.0
- `votes` is a list of agent decisions
- Each vote has `agent_name` and `action` fields

**Note on request shape:** FastAPI infers two body params (`intent` and `ctx`), so the JSON body must be `{"intent": {...}, "ctx": {...}}` — NOT a flat merge.

### `TestMetaAgent`
- POST `/meta-agent/evaluate` returns 200 (currently a stub; no assertions on body shape)

### `TestPipeline`

**Route:** `POST /pipeline/run` with `StrategyContext` body

- Returns 200
- Response has counter fields: `intents_generated`, `approved`, `rejected`, `enqueued`
- All counters are non-negative integers
- No HTTP-level errors in the `errors` list (strategy "no signal" messages are acceptable noise)

---

## Key Assertions

- **Regime with few candles:** `STRATEGY_CTX` has 3 candles → always returns `RANGE_BOUND` (confidence ≈ 0.3)
- **Regime with 30 candles:** `STRATEGY_CTX_30` has 30 uniform-price candles → ADX will be low → expect `RANGE_BOUND` but via the real ADX path (confidence > 0.3 possible)
- **Pipeline errors vs failures:** `errors` list may contain `"no signal"` strings (strategies that didn't fire) — these are NOT failures. Only HTTP 5xx or connection errors are failures.

---

## Dependencies

- Strategy service (port 3002) must be running — pipeline calls it
- Risk service (port 3003) must be running — pipeline calls approve
- Execution service (port 3004) must be running — pipeline enqueues
- Redis must be running
