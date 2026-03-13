"""
Strategy Service  —  port 3002
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plug-in strategy registry: DCA · Grid · Momentum (RSI) · MA-Crossover
Each strategy is stateless; last-trade timestamps live in Redis.
Signals are published to the Redis 'trading_os:signals' pub/sub channel.
"""

import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from trading_os.types.models import HealthCheck, StrategyContext, TradeIntent

from .backtest import BacktestRequest, BacktestResult, run_backtest
from .strategies.registry import REGISTRY

# ─── State ────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_start_time = time.time()


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await _redis.ping()
    names = list(REGISTRY.keys())
    print(f"✅  strategy: {len(names)} strategies loaded: {names}")
    yield
    await _redis.aclose()


app = FastAPI(title="strategy-service", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthCheck)
async def health():
    checks: dict = {}
    try:
        await _redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
    checks["strategies_loaded"] = str(len(REGISTRY))

    status = "ok" if checks.get("redis") == "ok" else "degraded"
    return HealthCheck(
        service="strategy",
        status=status,
        version="0.2.0",
        uptime=round(time.time() - _start_time, 1),
        checks=checks,
        timestamp=int(time.time() * 1000),
    )


# ─── Registry ─────────────────────────────────────────────────────────────────

@app.get("/strategies")
async def list_strategies():
    """Return all registered strategies with enabled state and default params."""
    result = []
    for name, strategy in REGISTRY.items():
        raw = await _redis.get(f"trading_os:strategy:enabled:{name}")
        enabled = raw != "0" if raw is not None else True
        result.append({
            "name": name,
            "description": strategy.description,
            "enabled": enabled,
            "default_params": strategy.default_params,
        })
    return result


@app.post("/strategies/{name}/enable")
async def enable_strategy(name: str):
    if name not in REGISTRY:
        raise HTTPException(404, f"Strategy '{name}' not found")
    await _redis.set(f"trading_os:strategy:enabled:{name}", "1")
    return {"name": name, "enabled": True}


@app.post("/strategies/{name}/disable")
async def disable_strategy(name: str):
    if name not in REGISTRY:
        raise HTTPException(404, f"Strategy '{name}' not found")
    await _redis.set(f"trading_os:strategy:enabled:{name}", "0")
    return {"name": name, "enabled": False}


# ─── Evaluate ─────────────────────────────────────────────────────────────────

@app.post("/strategies/{name}/evaluate")
async def evaluate_strategy(name: str, ctx: StrategyContext):
    """Run a single strategy against the provided context. Returns signal or null."""
    if name not in REGISTRY:
        raise HTTPException(404, f"Strategy '{name}' not found")

    strategy = REGISTRY[name]
    raw = await _redis.get(f"trading_os:last_trade:{name}:{ctx.pair.replace('/', '_')}")
    last_trade_at = int(raw) if raw else 0

    intent = await strategy.should_trade(ctx, last_trade_at)

    if intent:
        await _redis.set(
            f"trading_os:last_trade:{name}:{ctx.pair.replace('/', '_')}",
            str(int(time.time() * 1000)),
            ex=86_400 * 7,
        )
        await _redis.publish("trading_os:signals", intent.model_dump_json())

    return {
        "strategy": name,
        "pair": ctx.pair,
        "fired": intent is not None,
        "signal": intent.model_dump() if intent else None,
    }


# ─── Run all ─────────────────────────────────────────────────────────────────

@app.post("/run")
async def run_all_strategies(ctx: StrategyContext):
    """Run every enabled strategy against the context. Publishes all signals."""
    signals = 0
    results = []

    for name, strategy in REGISTRY.items():
        raw_enabled = await _redis.get(f"trading_os:strategy:enabled:{name}")
        if raw_enabled == "0":
            continue

        raw_lt = await _redis.get(f"trading_os:last_trade:{name}:{ctx.pair.replace('/', '_')}")
        last_trade_at = int(raw_lt) if raw_lt else 0

        try:
            intent = await strategy.should_trade(ctx, last_trade_at)
        except Exception as exc:
            results.append({"strategy": name, "error": str(exc)})
            continue

        if intent:
            signals += 1
            await _redis.set(
                f"trading_os:last_trade:{name}:{ctx.pair.replace('/', '_')}",
                str(int(time.time() * 1000)),
                ex=86_400 * 7,
            )
            await _redis.publish("trading_os:signals", intent.model_dump_json())
            results.append({"strategy": name, "fired": True, "signal": intent.model_dump()})
        else:
            results.append({"strategy": name, "fired": False})

    return {"signals_generated": signals, "results": results}


# ─── Backtest ─────────────────────────────────────────────────────────────────

@app.post("/backtest", response_model=BacktestResult)
async def backtest(req: BacktestRequest):
    """
    Run a bar-by-bar backtest on provided OHLCV data.
    Returns full performance metrics: Sharpe, drawdown, win rate, equity curve.
    """
    if req.strategy_name not in REGISTRY:
        raise HTTPException(404, f"Strategy '{req.strategy_name}' not found")
    strategy = REGISTRY[req.strategy_name]
    return await run_backtest(strategy, req)

