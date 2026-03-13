# Test Specification — Integration Tests

**Suite:** `integration`  
**File:** `test_pipeline.py`  
**Mark:** `@pytest.mark.integration`

---

## Purpose

Integration tests verify that the 6 microservices communicate correctly with each other over the Docker network and that data flows through the entire trading pipeline from end to end.

**These tests are NOT run by default.** To run them:

```bash
cd Backend
pytest -m integration
```

Unit/smoke tests can be run independently without any inter-service dependencies:

```bash
pytest -m "not integration"
```

---

## Architecture Under Test

```
Portfolio (/sync)
    │
    ▼  (prices → Redis)
Risk (/evaluate)
    │
    │  TradeIntent → [L1–L6 checks] → RiskDecision
    ▼
Risk (/approve)
    │
    │  RiskDecision + risk_decision_id → ApprovedTradeIntent
    ▼
Execution (/enqueue)
    │
    └─ Paper order receipt (is_paper: true)

─────────────────────────────────────────

Orchestrator (/pipeline/run)
    │
    ├─ → Strategy (/run)        [evaluate all strategies]
    ├─ → Orchestrator (/vote)   [mock agent vote]
    ├─ → Risk (/approve)        [approve each intent]
    └─ → Execution (/enqueue)   [queue all approved intents]
```

---

## Test Classes

### `TestPortfolioToRiskToExecution`

**Validates the core trade approval chain.**

| Test | What it proves |
|------|----------------|
| `test_risk_evaluate_accepts_small_intent` | L1–L5 pass for a small BTC trade |
| `test_approved_intent_can_be_enqueued` | Execution accepts an `ApprovedTradeIntent` |
| `test_full_portfolio_to_execution_chain` | End-to-end: sync → evaluate → approve → enqueue |

**Full chain test steps:**
1. **`POST /portfolio/sync`** — populate Redis with live prices
2. **`POST /risk/evaluate`** — send `INTENT_SMALL`; assert `approved: true`
3. **`POST /risk/approve`** — enrich intent with `risk_decision_id` from step 2
4. **`POST /execution/enqueue`** — assert `status: "queued"` and `is_paper: true`

### `TestOrchestratorPipeline`

**Validates that the orchestrator's internal service calls work.**

| Test | What it proves |
|------|----------------|
| `test_pipeline_returns_valid_response` | `/pipeline/run` returns counters without crashing |
| `test_pipeline_enqueued_lte_intents_generated` | Can't enqueue more than was generated |
| `test_pipeline_approved_lte_intents_generated` | Can't approve more than was generated |

### `TestKillSwitchPropagation`

**Validates that the kill-switch correctly blocks the pipeline.**

| Test | What it proves |
|------|----------------|
| `test_kill_switch_blocks_risk_evaluation` | After arming L6 kill-switch, risk rejects with `KILL_SWITCH` reason |

The `clear_kill_switch` fixture disarms the kill-switch after this test.

---

## Prerequisite Checklist

All 6 containers must be healthy before running integration tests:

```bash
docker compose ps
# All: portfolio, strategy, risk, execution, orchestrator, analytics → "healthy"
```

Verify individually:
```bash
curl localhost:3001/health  # portfolio
curl localhost:3002/health  # strategy
curl localhost:3003/health  # risk
curl localhost:3004/health  # execution
curl localhost:3005/health  # orchestrator
curl localhost:3006/health  # analytics
```

---

## Fixture Dependencies

- `http` — `httpx.Client` with 10s timeout (from `conftest.py`)
- `clear_kill_switch` — auto-disarms risk kill-switch before and after test

---

## Known Limitations

- Integration tests assume paper-trading mode (`is_paper: true` always)
- Kill-switch state is shared across tests; `clear_kill_switch` fixture ensures isolation
- Pipeline test uses `STRATEGY_CTX` with only 3 candles — most strategies won't fire; `intents_generated` may be 0
