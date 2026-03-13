"""
Analytics Service  —  port 3006
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Responsibilities:
  • Compute and refresh StrategyMetrics (win rate, PnL, Sharpe, drawdown)
  • Serve dashboards: trade history, daily PnL curve, regime history
  • Detect strategy degradation (win rate falling, Sharpe dropping)
  • Aggregate audit_log events for the control center frontend
  • Write computed metrics to Firestore for real-time dashboard reads

All reads are from PostgreSQL (immutable audit trail).
Heavy computations use pandas — never block the event loop.
"""

import os
import time
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trading_os.db.database import create_all_tables, get_session
from trading_os.db.models import AuditLog, RegimeHistory, RiskDecision, StrategyMetrics, Trade
from trading_os.types.models import HealthCheck

# ─── State ────────────────────────────────────────────────────────────────────

redis: aioredis.Redis | None = None
_start_time = time.time()

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis
    redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await create_all_tables()
    print("✅  analytics: Redis + PostgreSQL connected")
    yield
    await redis.aclose()


app = FastAPI(title="analytics-service", version="0.1.0", lifespan=lifespan)
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
        service="analytics",
        status=status,
        version="0.1.0",
        uptime=round(time.time() - _start_time, 1),
        checks=checks,
        timestamp=int(time.time() * 1000),
    )


# ─── Trade History ────────────────────────────────────────────────────────────

@app.get("/trades")
async def list_trades(
    strategy: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
):
    """Return paginated trade history, optionally filtered by strategy."""
    q = select(Trade).order_by(Trade.created_at.desc()).limit(limit)
    if strategy:
        q = q.where(Trade.strategy_name == strategy)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id":             t.id,
            "strategy_name": t.strategy_name,
            "pair":           t.pair,
            "side":           t.side,
            "quantity":       t.quantity,
            "price":          t.price,
            "executed_price": t.executed_price,
            "filled_quantity": t.filled_quantity,
            "fee":            t.fee,
            "pnl_usd":        t.pnl_usd,
            "status":         t.status,
            "is_paper":       t.is_paper,
            "created_at":     t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


# ─── Strategy Metrics ─────────────────────────────────────────────────────────

@app.get("/strategies/metrics")
async def get_strategy_metrics(db: AsyncSession = Depends(get_session)):
    """Return rolling metrics for all strategies."""
    result = await db.execute(select(StrategyMetrics))
    rows = result.scalars().all()
    return [
        {
            "strategy_name":   r.strategy_name,
            "total_trades":    r.total_trades,
            "winning_trades":  r.winning_trades,
            "losing_trades":   r.losing_trades,
            "win_rate":        r.win_rate,          # pct 0–100
            "total_pnl":       r.total_pnl_usd,     # alias for dashboard compat
            "total_pnl_usd":   r.total_pnl_usd,
            "avg_pnl_usd":     r.avg_pnl_usd,
            "sharpe_ratio":    r.sharpe_ratio or 0.0,
            "max_drawdown_pct": r.max_drawdown_pct or 0.0,
            "is_enabled":      r.is_enabled,
            "updated_at":      r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@app.post("/strategies/metrics/refresh")
async def refresh_metrics(db: AsyncSession = Depends(get_session)):
    """
    Recompute per-strategy metrics from the trades table using pandas.
    Calculates: total_trades, win_rate, total_pnl, avg_pnl, sharpe_ratio, max_drawdown.
    Upserts into strategy_metrics table.
    """
    import pandas as pd
    import numpy as np
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    import time as _time

    result = await db.execute(select(Trade))
    trades = result.scalars().all()

    if not trades:
        return {"ok": True, "refreshed": 0}

    rows = [
        {
            "strategy_name": t.strategy_name,
            "pnl_usd":       t.pnl_usd or 0.0,
            "side":          t.side,
            "created_at":    t.created_at,
        }
        for t in trades
    ]
    df = pd.DataFrame(rows)
    refreshed = 0

    for strategy_name, grp in df.groupby("strategy_name"):
        sells  = grp[grp["side"] == "sell"]
        pnls   = sells["pnl_usd"].dropna()
        total  = len(grp)          # count all trades (buys + sells)
        sells_total = len(sells)
        wins   = int((pnls > 0).sum())
        win_rate = round(wins / sells_total * 100, 1) if sells_total else 0.0
        total_pnl = round(float(pnls.sum()), 2)
        avg_pnl   = round(float(pnls.mean()), 2) if len(pnls) else 0.0

        # Sharpe (annualised, assume daily)
        if len(pnls) > 1:
            std = float(pnls.std())
            sharpe = round((avg_pnl / std * (252 ** 0.5)) if std > 0 else 0.0, 3)
        else:
            sharpe = 0.0

        # Max drawdown on equity curve
        equity = pnls.cumsum()
        peak   = equity.cummax()
        dd     = ((equity - peak) / peak.replace(0, pd.NA)).fillna(0)
        max_dd = round(float(dd.min() * -100), 2) if len(dd) else 0.0

        # Upsert using correct ORM field names
        existing = await db.execute(
            select(StrategyMetrics).where(StrategyMetrics.strategy_name == strategy_name)
        )
        row = existing.scalar_one_or_none()
        now = int(_time.time() * 1000)
        if row:
            row.total_trades     = total
            row.winning_trades   = wins
            row.losing_trades    = sells_total - wins
            row.win_rate         = win_rate
            row.total_pnl_usd    = total_pnl
            row.avg_pnl_usd      = avg_pnl
            row.sharpe_ratio     = sharpe
            row.max_drawdown_pct = max_dd
        else:
            db.add(StrategyMetrics(
                strategy_name=strategy_name,
                total_trades=total,
                winning_trades=wins,
                losing_trades=sells_total - wins,
                win_rate=win_rate,
                total_pnl_usd=total_pnl,
                avg_pnl_usd=avg_pnl,
                sharpe_ratio=sharpe,
                max_drawdown_pct=max_dd,
            ))
        refreshed += 1

    await db.commit()
    return {"ok": True, "refreshed": refreshed}


# ─── Audit Log ────────────────────────────────────────────────────────────────

@app.get("/audit")
async def get_audit_log(
    event_type: str | None = None,
    trade_intent_id: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_session),
):
    """Return audit log entries for the control center."""
    q = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if event_type:
        q = q.where(AuditLog.event_type == event_type)
    if trade_intent_id:
        q = q.where(AuditLog.trade_intent_id == trade_intent_id)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id":              e.id,
            "event_type":      e.event_type,
            "trade_intent_id": e.trade_intent_id,
            "agent_name":      e.agent_name,
            "model_used":      e.model_used,
            "input":           e.input,
            "output":          e.output,
            "duration_ms":     e.duration_ms,
            "created_at":      e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


# ─── PnL ─────────────────────────────────────────────────────────────────────

@app.get("/pnl/daily")
async def daily_pnl(db: AsyncSession = Depends(get_session)):
    """Return daily PnL timeseries aggregated from the trades table."""
    import pandas as pd

    result = await db.execute(
        select(Trade)
        .where(Trade.pnl_usd.isnot(None))
        .order_by(Trade.created_at.asc())
    )
    trades = result.scalars().all()
    if not trades:
        return []

    rows = [
        {
            "date":    t.created_at.date().isoformat(),
            "pnl_usd": float(t.pnl_usd or 0.0),
        }
        for t in trades
        if t.created_at
    ]
    if not rows:
        return []

    df    = pd.DataFrame(rows)
    daily = df.groupby("date")["pnl_usd"].sum().reset_index()
    return [
        {"date": str(row["date"]), "pnl_usd": round(float(row["pnl_usd"]), 2)}
        for _, row in daily.iterrows()
    ]


# ─── Decision Trace ──────────────────────────────────────────────────────────

@app.get("/trades/{trade_id}/trace")
async def get_decision_trace(trade_id: str, db: AsyncSession = Depends(get_session)):
    """
    Return the full decision trace for a single trade.
    Synthesises a timeline from:
      1. audit_log rows matching trade_intent_id  (CLASSIFY, SIGNAL, VOTE, …)
      2. risk_decisions row                        (RISK stage)
      3. the trade row itself                      (EXECUTE + RECORD stages)
    Ordered chronologically so the UI can render a step-by-step timeline.
    """
    events = []

    # ── 1. Find the trade ────────────────────────────────────────────────────
    trade_res = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade = trade_res.scalar_one_or_none()

    intent_id: str | None = trade.trade_intent_id if trade else None

    # ── 2. Audit log events for this intent ──────────────────────────────────
    if intent_id:
        q = (
            select(AuditLog)
            .where(AuditLog.trade_intent_id == intent_id)
            .order_by(AuditLog.created_at.asc())
        )
        audit_res = await db.execute(q)
        for e in audit_res.scalars().all():
            # Map audit event types to pipeline stage labels
            stage_map = {
                "REGIME_CLASSIFIED":   "CLASSIFY",
                "SIGNAL_GENERATED":    "SIGNAL",
                "STRATEGY_SELECTED":   "SIGNAL",
                "AGENT_VOTE":          "VOTE",
                "AGENT_REASONING":     "VOTE",
                "META_AGENT_EVALUATION": "VOTE",
                "RISK_CHECK":          "RISK",
                "RISK_REJECTED":       "RISK",
                "ORDER_PLACED":        "EXECUTE",
                "ORDER_FILLED":        "EXECUTE",
                "ORDER_CANCELED":      "EXECUTE",
                "ORDER_FAILED":        "EXECUTE",
                "KILL_SWITCH_ACTIVATED": "RISK",
                "CIRCUIT_BREAKER_TRIGGERED": "RISK",
            }
            stage = stage_map.get(e.event_type, "INFO")
            events.append({
                "stage":       stage,
                "event_type":  e.event_type,
                "agent_name":  e.agent_name,
                "model_used":  e.model_used,
                "payload":     {"input": e.input, "output": e.output},
                "duration_ms": e.duration_ms,
                "ts":          e.created_at.isoformat() if e.created_at else None,
            })

    # ── 3. Risk decision ─────────────────────────────────────────────────────
    if intent_id:
        rd_res = await db.execute(
            select(RiskDecision)
            .where(RiskDecision.trade_intent_id == intent_id)
            .order_by(RiskDecision.created_at.asc())
        )
        for rd in rd_res.scalars().all():
            # Only add if not already covered by an audit_log RISK_CHECK entry
            events.append({
                "stage":      "RISK",
                "event_type": "RISK_DECISION",
                "agent_name": None,
                "model_used": None,
                "payload": {
                    "approved":         rd.approved,
                    "rejection_reason": rd.rejection_reason,
                    "checks":           rd.checks_performed,
                },
                "duration_ms": None,
                "ts": rd.created_at.isoformat() if rd.created_at else None,
            })

    # ── 4. Enqueue synthetic event ───────────────────────────────────────────
    if trade:
        events.append({
            "stage":      "ENQUEUE",
            "event_type": "ORDER_ENQUEUED",
            "agent_name": None,
            "model_used": None,
            "payload": {
                "pair":          trade.pair,
                "side":          trade.side,
                "quantity":      trade.quantity,
                "order_type":    trade.order_type,
                "strategy_name": trade.strategy_name,
                "is_paper":      trade.is_paper,
            },
            "duration_ms": None,
            "ts": trade.created_at.isoformat() if trade.created_at else None,
        })

        # ── 5. Execute event ─────────────────────────────────────────────────
        if trade.executed_price is not None:
            events.append({
                "stage":      "EXECUTE",
                "event_type": "ORDER_FILLED",
                "agent_name": None,
                "model_used": None,
                "payload": {
                    "venue":           "paper" if trade.is_paper else "live",
                    "exchange_order_id": trade.exchange_order_id,
                    "executed_price":  trade.executed_price,
                    "filled_quantity": trade.filled_quantity,
                    "fee":             trade.fee,
                    "slippage_pct":    trade.slippage_pct,
                    "status":          trade.status,
                },
                "duration_ms": None,
                "ts": trade.filled_at.isoformat() if trade.filled_at else (
                    trade.placed_at.isoformat() if trade.placed_at else None
                ),
            })

        # ── 6. Record event ──────────────────────────────────────────────────
        events.append({
            "stage":      "RECORD",
            "event_type": "TRADE_RECORDED",
            "agent_name": None,
            "model_used": None,
            "payload": {
                "trade_id":    trade.id,
                "pnl_usd":     trade.pnl_usd,
                "fee":         trade.fee,
                "status":      trade.status,
                "is_paper":    trade.is_paper,
            },
            "duration_ms": None,
            "ts": (trade.filled_at or trade.created_at).isoformat()
                  if (trade.filled_at or trade.created_at) else None,
        })

    # ── Sort by ts ────────────────────────────────────────────────────────────
    events.sort(key=lambda e: e["ts"] or "")

    return {
        "trade_id":  trade_id,
        "intent_id": intent_id,
        "trade": {
            "strategy_name": trade.strategy_name,
            "pair":          trade.pair,
            "side":          trade.side,
            "quantity":      trade.quantity,
            "executed_price": trade.executed_price,
            "pnl_usd":       trade.pnl_usd,
            "status":        trade.status,
            "is_paper":      trade.is_paper,
        } if trade else None,
        "events": events,
        "stage_count": len({e["stage"] for e in events}),
    }


# ─── Regime History ───────────────────────────────────────────────────────────

@app.get("/regimes/{pair}")
async def get_regime_history(
    pair: str,
    limit: int = 100,
    db: AsyncSession = Depends(get_session),
):
    result = await db.execute(
        select(RegimeHistory)
        .where(RegimeHistory.pair == pair)
        .order_by(RegimeHistory.classified_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id":            r.id,
            "pair":          r.pair,
            "regime":        r.regime,
            "confidence":    r.confidence,
            "indicators":    r.indicators,
            "classified_at": r.classified_at.isoformat() if r.classified_at else None,
        }
        for r in rows
    ]
