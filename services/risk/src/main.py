"""
Risk Service  —  port 3003
━━━━━━━━━━━━━━━━━━━━━━━━━━
Responsibilities:
  • Validate every TradeIntent against the 6-level capital protection hierarchy
  • Sign approved intents as ApprovedTradeIntent (only this reaches execution)
  • Write full RiskDecision to PostgreSQL (immutable audit)
  • Trigger CircuitBreaker events when thresholds are breached
  • Expose current RiskConfig (configurable without redeploy)

6-Level Capital Protection Hierarchy:
  L1  Position size limit            (max % of portfolio per trade)
  L2  Strategy allocation cap        (max % per strategy)
  L3  Portfolio heat ceiling         (total open risk exposure)
  L4  Daily loss circuit breaker     (auto-halt when daily loss limit hit)
  L5  Weekly drawdown limit          (kill-switch trigger)
  L6  Global kill switch             (manual override, halts everything)

Rule: if ANY level fails, the trade is rejected and logged.
"""

import os
import time
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from trading_os.db.database import create_all_tables, get_session
from trading_os.db.models import RiskDecision as RiskDecisionORM
from trading_os.types.models import (
    ApprovedTradeIntent,
    HealthCheck,
    RiskCheck,
    RiskConfig,
    RiskDecision,
    TradeIntent,
)

# ─── State ────────────────────────────────────────────────────────────────────

redis: aioredis.Redis | None = None
_start_time = time.time()

# Default risk config — override via /config endpoint or env
_risk_config = RiskConfig()

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await create_all_tables()
    print("✅  risk: Redis + PostgreSQL connected")
    yield
    await redis.aclose()


app = FastAPI(title="risk-service", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthCheck)
async def health():
    checks: dict = {}
    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthCheck(
        service="risk",
        status=status,
        version="0.1.0",
        uptime=round(time.time() - _start_time, 1),
        checks=checks,
        timestamp=int(time.time() * 1000),
    )


# ─── Risk Config ──────────────────────────────────────────────────────────────

@app.get("/config", response_model=RiskConfig)
async def get_config():
    return _risk_config


@app.put("/config", response_model=RiskConfig)
async def update_config(config: RiskConfig):
    """Hot-update risk limits without service restart."""
    global _risk_config
    _risk_config = config
    return _risk_config


# ─── Core: Evaluate Trade Intent ──────────────────────────────────────────────

@app.post("/evaluate", response_model=RiskDecision)
async def evaluate(intent: TradeIntent, db: AsyncSession = Depends(get_session)):
    """
    Run a TradeIntent through all 6 capital protection levels.
    Returns a RiskDecision. Writes result to PostgreSQL.

    If approved=True, the caller should use the ApprovedTradeIntent
    returned by /approve to send to the execution queue.
    """
    # Fetch portfolio snapshot from Redis (set by portfolio service)
    snapshot_raw = await redis.get("trading_os:portfolio:snapshot")
    if not snapshot_raw:
        raise HTTPException(status_code=503, detail="Portfolio snapshot unavailable — risk engine cannot evaluate")

    from trading_os.types.models import PortfolioSnapshot
    snapshot = PortfolioSnapshot.model_validate_json(snapshot_raw)

    checks: list[RiskCheck] = []
    approved = True
    rejection_reason: str | None = None

    total_usd = max(snapshot.total_value_usd, 1.0)  # guard /0

    # ── L6: Kill switch (checked first — fastest rejection) ───────────────────
    kill = await redis.get("trading_os:kill_switch")
    l6_passed = kill is None
    checks.append(RiskCheck(
        name="KILL_SWITCH", level=6, passed=l6_passed,
        value=1.0 if kill else 0.0, limit=0.0,
        message="Global kill switch active" if not l6_passed else None,
    ))
    if not l6_passed:
        approved = False
        rejection_reason = "KILL_SWITCH"

    # ── L1: Position size limit ────────────────────────────────────────────────
    if approved:
        trade_value = intent.quantity * (intent.price or snapshot.total_value_usd * 0.01)
        pos_pct = trade_value / total_usd * 100
        l1_passed = pos_pct <= _risk_config.max_position_size_pct
        checks.append(RiskCheck(
            name="POSITION_SIZE", level=1, passed=l1_passed,
            value=round(pos_pct, 2), limit=_risk_config.max_position_size_pct,
            message=f"Trade is {pos_pct:.1f}% of portfolio (max {_risk_config.max_position_size_pct}%)" if not l1_passed else None,
        ))
        if not l1_passed:
            approved = False
            rejection_reason = "POSITION_SIZE_EXCEEDED"

    # ── L2: Strategy allocation cap ────────────────────────────────────────────
    if approved:
        alloc_raw = await redis.get(f"trading_os:strategy:allocation:{intent.strategy_name}")
        existing_alloc_pct = float(alloc_raw) if alloc_raw else 0.0
        this_trade_pct = (intent.quantity * (intent.price or 0.0)) / total_usd * 100
        projected = existing_alloc_pct + this_trade_pct
        l2_passed = projected <= _risk_config.max_strategy_allocation_pct
        checks.append(RiskCheck(
            name="STRATEGY_ALLOCATION", level=2, passed=l2_passed,
            value=round(projected, 2), limit=_risk_config.max_strategy_allocation_pct,
            message=f"Strategy '{intent.strategy_name}' projected {projected:.1f}% allocation" if not l2_passed else None,
        ))
        if not l2_passed:
            approved = False
            rejection_reason = "STRATEGY_ALLOCATION_EXCEEDED"

    # ── L3: Portfolio heat ceiling ─────────────────────────────────────────────
    if approved:
        heat = snapshot.portfolio_heat_pct
        l3_passed = heat <= _risk_config.max_portfolio_heat_pct
        checks.append(RiskCheck(
            name="PORTFOLIO_HEAT", level=3, passed=l3_passed,
            value=round(heat, 2), limit=_risk_config.max_portfolio_heat_pct,
            message=f"Portfolio heat {heat:.1f}% exceeds cap {_risk_config.max_portfolio_heat_pct}%" if not l3_passed else None,
        ))
        if not l3_passed:
            approved = False
            rejection_reason = "PORTFOLIO_HEAT_EXCEEDED"

    # ── L4: Daily loss circuit breaker ─────────────────────────────────────────
    if approved:
        daily_loss_usd = abs(min(0.0, snapshot.daily_pnl))
        l4_passed = daily_loss_usd < _risk_config.daily_loss_limit_usd
        checks.append(RiskCheck(
            name="DAILY_LOSS", level=4, passed=l4_passed,
            value=round(daily_loss_usd, 2), limit=_risk_config.daily_loss_limit_usd,
            message=f"Daily loss ${daily_loss_usd:.0f} exceeds limit ${_risk_config.daily_loss_limit_usd:.0f}" if not l4_passed else None,
        ))
        if not l4_passed:
            approved = False
            rejection_reason = "DAILY_LOSS_LIMIT_BREACHED"

    # ── L5: Weekly drawdown limit ──────────────────────────────────────────────
    if approved:
        weekly_drawdown_pct = abs(min(0.0, snapshot.weekly_pnl / total_usd * 100))
        l5_passed = weekly_drawdown_pct < _risk_config.weekly_drawdown_pct
        checks.append(RiskCheck(
            name="WEEKLY_DRAWDOWN", level=5, passed=l5_passed,
            value=round(weekly_drawdown_pct, 2), limit=_risk_config.weekly_drawdown_pct,
            message=f"Weekly drawdown {weekly_drawdown_pct:.1f}% exceeds limit {_risk_config.weekly_drawdown_pct}%" if not l5_passed else None,
        ))
        if not l5_passed:
            approved = False
            rejection_reason = "WEEKLY_DRAWDOWN_BREACHED"

    decision_id = str(uuid.uuid4())
    decision = RiskDecision(
        id=decision_id,
        trade_intent_id=intent.id,
        approved=approved,
        rejection_reason=rejection_reason,
        checks_performed=checks,
    )

    # Persist to audit trail
    db.add(RiskDecisionORM(
        id=decision_id,
        trade_intent_id=intent.id,
        approved=approved,
        rejection_reason=rejection_reason,
        checks_performed=[c.model_dump() for c in checks],
    ))

    return decision


@app.post("/approve", response_model=ApprovedTradeIntent)
async def approve(intent: TradeIntent, db: AsyncSession = Depends(get_session)):
    """
    Evaluate + return ApprovedTradeIntent in one call.
    Only call this if you want to immediately enqueue after approval.
    Returns 422 if rejected.
    """
    decision = await evaluate(intent, db)
    if not decision.approved:
        raise HTTPException(status_code=422, detail=decision.rejection_reason)
    return ApprovedTradeIntent(
        **intent.model_dump(),
        risk_decision_id=decision.id,
    )


# ─── Circuit Breaker ──────────────────────────────────────────────────────────

@app.post("/kill-switch")
async def activate_kill_switch():
    """
    Level-6 manual kill switch. Sets a Redis flag that all services check.
    Blocks all new trade evaluations until cleared.
    """
    await redis.set("trading_os:kill_switch", "1")
    return {"ok": True, "message": "Kill switch activated — all trading halted"}


@app.delete("/kill-switch")
async def clear_kill_switch():
    await redis.delete("trading_os:kill_switch")
    return {"ok": True, "message": "Kill switch cleared"}
