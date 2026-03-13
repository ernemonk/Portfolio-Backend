# Test Specification — Strategy Service

**Service:** `strategy`  
**Port:** `3002`  
**File:** `test_strategy.py`

---

## What This Service Does

The strategy service manages and executes multiple trading strategy algorithms. Each strategy can be enabled/disabled at runtime, evaluated against live market context, and backtested against historical OHLCV data.

**Strategies implemented:**

| Name | Logic |
|------|-------|
| `dca` | Dollar-cost averaging at fixed intervals — always fires, size = fixed amount |
| `grid` | Grid trading — fires when price crosses grid levels |
| `momentum` | RSI-based momentum — fires when RSI > 70 (overbought) or < 30 (oversold) |
| `ma_crossover` | EMA 9/21 crossover — fires on golden cross or death cross |

---

## Endpoints Tested

| Method | Path | What we test |
|--------|------|-------------|
| `GET` | `/health` | Service alive |
| `GET` | `/strategies` | Returns list of all registered strategies |
| `POST` | `/strategies/{name}/enable` | Enables a strategy |
| `POST` | `/strategies/{name}/disable` | Disables a strategy |
| `POST` | `/strategies/{name}/evaluate` | Runs one strategy against a `StrategyContext` |
| `POST` | `/backtest` | Runs a strategy over historical OHLCV in memory |
| `POST` | `/run` | Evaluates all enabled strategies, returns all signals |

---

## Test Classes

### `TestHealth`
- Service returns 200 with `"service": "strategy"`

### `TestStrategyList`
- GET `/strategies` returns a list with at least 1 item
- Each item has `name` and `enabled` fields
- All 4 strategy names are present: `dca`, `grid`, `momentum`, `ma_crossover`

### `TestEnableDisable`
- Enable a strategy → `{"ok": true}`
- Disable a strategy → `{"ok": true}`
- After disable, strategy list shows `"enabled": false` for that strategy
- Re-enable restores `"enabled": true`

### `TestEvaluate`
- All 4 strategies return 200 when evaluated
- Response has `strategy`, `pair`, `fired`, `signal` fields
- `fired` is a boolean
- `signal` is either `null` or a dict with trade intent fields
- DCA with `interval_hours=0` should always fire (forces immediate trigger)
- When `fired=true`, `signal` contains `pair`, `side`, `size`, `strategy_name`

### `TestBacktest`
- DCA backtest with 30 candles returns 200
- Grid backtest with 30 candles returns 200
- Momentum backtest returns `total_trades` and `win_rate`
- Win rate is between 0.0 and 1.0

### `TestRunAll`
- POST `/run` returns 200
- Response `signals` field is a list
- Each signal item matches evaluate response shape
- Running with 30+ candles triggers at least one DCA signal

---

## Key Assertions

- **Schema:** Response from `/strategies/{name}/evaluate` is `{"strategy": str, "pair": str, "fired": bool, "signal": obj|null}`
- **DCA always fires:** `interval_hours=0` in the context removes the cooldown guard, ensuring `fired=true` in tests
- **Signal completeness:** When `fired=true`, `signal.pair == context.pair` and `signal.strategy_name == strategy_name`
- **`ohlcv` field:** `StrategyContext.ohlcv` is the correct field name. Sending `candles` causes a silent empty list.

---

## Dependencies

- No Redis dependency (strategies are stateless for evaluation)
- Backtest runs fully in-process — no external calls
