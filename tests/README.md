# Backend Test Suite

Organized pytest suite covering all 6 microservices, with each service in its own folder containing a test file and a specification document.

---

## Folder Structure

```
tests/
├── README.md                  ← you are here
├── conftest.py                ← shared pytest fixtures (http client, URLs, kill-switch)
├── __init__.py
│
├── shared/
│   ├── fixtures.py            ← all canonical request payloads (single source of truth)
│   ├── SPEC.md                ← explains every constant and design decision
│   └── __init__.py
│
├── portfolio/                 ← port 3001
│   ├── test_portfolio.py
│   ├── SPEC.md
│   └── __init__.py
│
├── strategy/                  ← port 3002
│   ├── test_strategy.py
│   ├── SPEC.md
│   └── __init__.py
│
├── risk/                      ← port 3003
│   ├── test_risk.py
│   ├── SPEC.md
│   └── __init__.py
│
├── execution/                 ← port 3004
│   ├── test_execution.py
│   ├── SPEC.md
│   └── __init__.py
│
├── orchestrator/              ← port 3005
│   ├── test_orchestrator.py
│   ├── SPEC.md
│   └── __init__.py
│
├── analytics/                 ← port 3006
│   ├── test_analytics.py
│   ├── SPEC.md
│   └── __init__.py
│
└── integration/               ← cross-service end-to-end
    ├── test_pipeline.py
    ├── SPEC.md
    └── __init__.py
```

---

## Prerequisites

All 6 Docker containers must be running and healthy:

```bash
cd Backend
docker compose --context desktop-linux up -d
docker compose --context desktop-linux ps
```

Expected: `portfolio`, `strategy`, `risk`, `execution`, `orchestrator`, `analytics` all showing `healthy`.

---

## How to Run

### Run everything (smoke + unit, no integration)
```bash
cd Backend
pytest
```

### Run a single service
```bash
pytest tests/portfolio/
pytest tests/risk/
pytest tests/orchestrator/
```

### Run only smoke tests (fastest)
```bash
pytest -m smoke
```

### Run integration tests (requires all services healthy)
```bash
pytest -m integration
```

### Run everything including integration
```bash
pytest -m "smoke or unit or integration"
```

### Verbose output
```bash
pytest -v tests/risk/
```

### Stop on first failure
```bash
pytest -x
```

---

## Test Marks

Defined in `pytest.ini`:

| Mark | Meaning |
|------|---------|
| `smoke` | Basic health + shape assertions — fast, no side effects |
| `unit` | Logic assertions within one service — no cross-service calls |
| `integration` | Cross-service calls; all containers must be running |
| `slow` | Tests with deliberate delays (e.g., waiting for background sync) |

---

## Service Port Map

| Service | Port | Env var |
|---------|------|---------|
| portfolio | 3001 | `PORTFOLIO_URL` |
| strategy | 3002 | `STRATEGY_URL` |
| risk | 3003 | `RISK_URL` |
| execution | 3004 | `EXECUTION_URL` |
| orchestrator | 3005 | `ORCHESTRATOR_URL` |
| analytics | 3006 | `ANALYTICS_URL` |

Defaults are defined in `tests/shared/fixtures.py`. Override via environment variables to test against a remote stack.

---

## Test Count Summary

| Service | Tests | Classes |
|---------|-------|---------|
| portfolio | ~20 | 7 |
| strategy | ~21 | 6 |
| risk | ~22 | 5 |
| execution | ~11 | 3 |
| orchestrator | ~20 | 5 |
| analytics | ~14 | 6 |
| integration | ~8 | 3 |
| **Total** | **~116** | **35** |

---

## Key Design Decisions

1. **Single fixtures file** — `tests/shared/fixtures.py` is the only place API payloads are defined. Schema change = one edit.
2. **`ohlcv` not `candles`** — The `StrategyContext` Pydantic model uses `ohlcv`. Sending `candles` silently passes validation as an empty list.
3. **`risk_decision_id` in execution** — `ApprovedTradeIntent` requires this field. A plain `TradeIntent` sent to `/enqueue` returns 422.
4. **Kill-switch isolation** — The `clear_kill_switch` fixture in `conftest.py` calls `DELETE /kill-switch` both before and after each test that touches it.
5. **Integration tests are opt-in** — Marked `@pytest.mark.integration` and excluded from the default `pytest` run to keep CI fast.
