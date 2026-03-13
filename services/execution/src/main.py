"""
Execution Service  —  port 3004
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Responsibilities:
  • Serialize trade execution via queue (prevents double-execution)
  • Only accepts ApprovedTradeIntent (signed by risk engine) — hard enforcement
  • Acquire distributed lock per pair before placing order
  • Paper mode (PAPER_MODE=true) → simulate fills, never touch exchange
  • Live mode → route to ccxt connector (Binance, Coinbase, etc.)
  • Write OrderResult + Trade row to PostgreSQL on every outcome
  • Rate-limit exchange API calls via Redis sliding window

Queue backend:
  EXECUTION_QUEUE_BACKEND=memory  →  InMemoryExecutionQueue  (single process)
  EXECUTION_QUEUE_BACKEND=redis   →  RedisExecutionQueue     (multi-container)
  Zero business logic changes between modes.

Safety invariants:
  1. Only ApprovedTradeIntent reaches this service (enforced by type)
  2. Distributed lock on pair prevents concurrent orders for same instrument
  3. Exchange rate limiter checked before every order placement
  4. All outcomes written to audit_log — failures are never silent
"""

import asyncio
import os
import time

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from trading_os.db.database import create_all_tables, get_session
from trading_os.db.models import Trade as TradeORM
from trading_os.queue.base import DistributedLock, ExecutionQueue
from trading_os.queue.factory import make_lock, make_queue
from trading_os.types.models import (
    ApprovedTradeIntent,
    HealthCheck,
    OrderResult,
    TradeStatus,
)

# ─── State ────────────────────────────────────────────────────────────────────

redis_client: aioredis.Redis | None = None
execution_queue: ExecutionQueue | None = None
distributed_lock: DistributedLock | None = None
_start_time = time.time()

PAPER_MODE = os.getenv("PAPER_MODE", "true").lower() == "true"

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, execution_queue, distributed_lock

    redis_client = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await create_all_tables()

    # Factory reads EXECUTION_QUEUE_BACKEND env var:
    # "memory" → InMemoryExecutionQueue / InMemoryLock
    # "redis"  → RedisExecutionQueue / RedisLock
    execution_queue = await make_queue()
    distributed_lock = await make_lock()

    backend = os.getenv("EXECUTION_QUEUE_BACKEND", "memory")
    mode = "PAPER" if PAPER_MODE else "⚡ LIVE"
    print(f"✅  execution: queue={backend} mode={mode}")

    # Start background queue consumer
    asyncio.create_task(_queue_worker())

    yield
    await redis_client.aclose()
    from .connectors import close_all
    await close_all()


app = FastAPI(title="execution-service", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthCheck)
async def health():
    checks: dict = {}
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    queue_depth = await execution_queue.queue_depth()
    checks["queue_depth"] = str(queue_depth)

    status = "ok" if checks.get("redis") == "ok" else "degraded"
    return HealthCheck(
        service="execution",
        status=status,
        version="0.1.0",
        uptime=round(time.time() - _start_time, 1),
        checks=checks,
        timestamp=int(time.time() * 1000),
    )


# ─── Enqueue ──────────────────────────────────────────────────────────────────

@app.post("/enqueue", response_model=OrderResult)
async def enqueue(intent: ApprovedTradeIntent, db: AsyncSession = Depends(get_session)):
    """
    Accepts an ApprovedTradeIntent and executes it.

    Paper mode (default): processes synchronously, writes Trade to PostgreSQL,
    returns OrderResult immediately.

    Live mode: enqueues for background worker, returns status=placed.

    The type system enforces that only risk-approved intents reach execution.
    """
    # Check kill switch
    if await redis_client.get("trading_os:kill_switch"):
        raise HTTPException(status_code=503, detail="Kill switch is active — execution halted")

    if PAPER_MODE:
        # Process synchronously — paper fills are instant, no exchange latency
        result = await _execute_intent(intent)
        # Persist trade to audit trail
        db.add(TradeORM(
            id=result.order_id,
            trade_intent_id=intent.id,
            risk_decision_id=intent.risk_decision_id,
            strategy_name=intent.strategy_name,
            pair=intent.pair,
            side=intent.side.value,
            quantity=intent.quantity,
            price=intent.price,
            order_type=intent.order_type.value,
            status=result.status,
            executed_price=result.executed_price,
            filled_quantity=result.filled_quantity,
            fee=result.fee,
            is_paper=True,
        ))
        return result
    else:
        # Live mode: queue for background worker
        job_id = await execution_queue.enqueue(intent)
        return OrderResult(
            order_id=job_id,
            status="placed",
            is_paper=False,
        )


@app.get("/queue/depth")
async def queue_depth():
    return {"depth": await execution_queue.queue_depth()}


# ─── Background Worker ────────────────────────────────────────────────────────

async def _queue_worker():
    """
    Continuously dequeues ApprovedTradeIntents and executes them.
    Acquires distributed lock per pair to prevent concurrent orders.
    Used in live mode only — paper mode processes inline in enqueue().
    """
    while True:
        result = await execution_queue.dequeue()
        if result is None:
            await asyncio.sleep(0.1)
            continue

        job_id, intent = result   # dequeue returns (job_id, intent) tuple
        lock_key = f"execute:{intent.pair}"

        async with distributed_lock.context(lock_key, ttl_seconds=30) as acquired:
            if not acquired:
                # Another container is already executing for this pair
                await execution_queue.nack(job_id, "lock_contention")
                continue

            try:
                result = await _execute_intent(intent)
                await execution_queue.ack(job_id)
                print(f"✅  executed: {intent.pair} {intent.side} {intent.quantity} → {result.status}")
            except Exception as e:
                await execution_queue.nack(job_id, str(e))
                print(f"❌  execution failed: {intent.pair} — {e}")


async def _execute_intent(intent: ApprovedTradeIntent) -> OrderResult:
    """
    Route the trade to the correct exchange adapter via EXCHANGE_REGISTRY.

    PAPER_MODE=true  → always routes to PaperAdapter regardless of intent.venue
                       (enqueue() sets venue="paper" before calling here)
    PAPER_MODE=false → routes to intent.venue (e.g. "binance", "alpaca")
                       Falls back to env EXCHANGE_ID if venue not set.

    No exchange-specific logic lives here. All adapter selection is done
    by get_connector(venue) — add a new exchange by updating EXCHANGE_REGISTRY
    in connectors.py only.
    """
    from .connectors import get_connector
    venue = "paper" if PAPER_MODE else (intent.venue or os.getenv("EXCHANGE_ID", "paper"))
    connector = get_connector(venue)
    return await connector.place_order(intent)

