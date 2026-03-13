"""
Orchestrator Service  —  port 3005
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Responsibilities:
  • Coordinate the full trade pipeline: market data → strategies → risk → execution
  • Host the multi-agent voting layer (LLM agents vote EXECUTE / SKIP)
  • Route to correct model provider (mock → anthropic → openai)
  • Meta-agent: evaluate strategy performance, suggest param adjustments
  • Regime classifier: label current market regime (TRENDING_UP, RANGE_BOUND …)
  • Publish all reasoning to audit_log via analytics service

Regime Classification (pure Python, no TA-Lib):
  - ADX > 25 + +DI > -DI  → TRENDING_UP
  - ADX > 25 + -DI > +DI  → TRENDING_DOWN
  - ATR/price > 5%         → HIGH_VOLATILITY_EVENT
  - else                   → RANGE_BOUND

Voting flow:
  1. Strategy fires TradeIntent
  2. Orchestrator broadcasts to N agents
  3. Each agent votes EXECUTE or SKIP with confidence + reasoning
  4. VoteResult computed (consensus threshold configurable)
  5. If EXECUTE + confidence > threshold → forward to risk service
  6. Risk service makes final binary approved/rejected decision
"""

import json
import os
import random
import time
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from trading_os.types.models import (
    AgentVote,
    HealthCheck,
    MarketRegime,
    OHLCV,
    PortfolioSnapshot,
    RegimeClassification,
    StrategyContext,
    TradeSide,
    TradeIntent,
    VoteResult,
)

# ─── Service URLs ─────────────────────────────────────────────────────────────

STRATEGY_URL  = os.getenv("STRATEGY_SERVICE_URL",  "http://strategy:3002")
RISK_URL      = os.getenv("RISK_SERVICE_URL",       "http://risk:3003")
EXECUTION_URL = os.getenv("EXECUTION_SERVICE_URL",  "http://execution:3004")

# ─── State ────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_http:  httpx.AsyncClient | None = None
_start_time = time.time()
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "mock")

# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _http
    _redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await _redis.ping()
    _http = httpx.AsyncClient(timeout=10.0)
    print(f"✅  orchestrator: Redis connected (model_provider={MODEL_PROVIDER})")
    yield
    await _redis.aclose()
    await _http.aclose()


app = FastAPI(title="orchestrator-service", version="0.2.0", lifespan=lifespan)
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
    checks["model_provider"] = MODEL_PROVIDER

    status = "ok" if checks.get("redis") == "ok" else "degraded"
    return HealthCheck(
        service="orchestrator",
        status=status,
        version="0.2.0",
        uptime=round(time.time() - _start_time, 1),
        checks=checks,
        timestamp=int(time.time() * 1000),
    )


# ─── Regime Classifier ───────────────────────────────────────────────────────

def _true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def _atr(candles: list[OHLCV], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    trs = [_true_range(candles[i].high, candles[i].low, candles[i - 1].close) for i in range(1, len(candles))]
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _wilder_smooth(data: list[float], n: int) -> list[float]:
    if len(data) < n:
        return [sum(data) / len(data)] if data else [0.0]
    smoothed = sum(data[:n])
    result = [smoothed]
    for d in data[n:]:
        smoothed = smoothed - smoothed / n + d
        result.append(smoothed)
    return result


def _adx_dmi(candles: list[OHLCV], period: int = 14) -> tuple[float, float, float]:
    """Return (ADX, +DI, -DI). Requires at least 2*period candles."""
    if len(candles) < period * 2:
        return 0.0, 0.0, 0.0

    dm_plus, dm_minus, trs = [], [], []
    for i in range(1, len(candles)):
        up   = candles[i].high - candles[i - 1].high
        down = candles[i - 1].low - candles[i].low
        dm_plus.append(up if up > down and up > 0 else 0.0)
        dm_minus.append(down if down > up and down > 0 else 0.0)
        trs.append(_true_range(candles[i].high, candles[i].low, candles[i - 1].close))

    sm_tr  = _wilder_smooth(trs, period)
    sm_dmp = _wilder_smooth(dm_plus, period)
    sm_dmm = _wilder_smooth(dm_minus, period)

    dx_vals = []
    di_plus_last = di_minus_last = 0.0
    for i in range(len(sm_tr)):
        if sm_tr[i] == 0:
            continue
        dip = 100 * sm_dmp[i] / sm_tr[i]
        dim = 100 * sm_dmm[i] / sm_tr[i]
        di_plus_last, di_minus_last = dip, dim
        denom = dip + dim
        dx_vals.append(100 * abs(dip - dim) / denom if denom > 0 else 0.0)

    if not dx_vals:
        return 0.0, di_plus_last, di_minus_last

    adx = sum(dx_vals[-period:]) / min(period, len(dx_vals))
    return round(adx, 2), round(di_plus_last, 2), round(di_minus_last, 2)


def _classify(candles: list[OHLCV], current_price: float) -> RegimeClassification:
    pair = "UNKNOWN"  # pair passed separately
    if len(candles) < 30:
        return RegimeClassification(
            pair=pair, regime=MarketRegime.RANGE_BOUND,
            confidence=0.3, atr=0.0, volatility_pct=0.0,
            indicators={"note": "insufficient_candles"},
        )

    atr = _atr(candles, 14)
    adx, di_plus, di_minus = _adx_dmi(candles, 14)
    volatility_pct = (atr / current_price * 100) if current_price > 0 else 0.0

    # Volume spike: last bar volume > 2× 20-bar average
    vols = [c.volume for c in candles[-21:]]
    avg_vol = sum(vols[:-1]) / max(len(vols) - 1, 1)
    volume_spike = vols[-1] > avg_vol * 2.0 if avg_vol > 0 else False

    # Classify
    if volatility_pct > 5.0 or (volume_spike and adx > 20):
        regime = MarketRegime.HIGH_VOLATILITY_EVENT
        confidence = min(0.95, volatility_pct / 10)
    elif adx > 25 and di_plus > di_minus:
        regime = MarketRegime.TRENDING_UP
        confidence = min(0.95, adx / 60)
    elif adx > 25 and di_minus > di_plus:
        regime = MarketRegime.TRENDING_DOWN
        confidence = min(0.95, adx / 60)
    else:
        regime = MarketRegime.RANGE_BOUND
        confidence = min(0.90, max(0.4, 1 - adx / 25))

    return RegimeClassification(
        pair=pair,
        regime=regime,
        confidence=round(confidence, 3),
        atr=round(atr, 4),
        volatility_pct=round(volatility_pct, 2),
        volume_spike=volume_spike,
        trend_strength=adx,
        indicators={"adx": adx, "di_plus": di_plus, "di_minus": di_minus},
    )


@app.post("/classify-regime", response_model=RegimeClassification)
async def classify_regime(pair: str, ctx: StrategyContext):
    """
    Classify current market regime. Cached in Redis for 5 minutes.
    Uses pure-Python ADX + ATR + volume-spike analysis.
    """
    cache_key = f"trading_os:regime:{pair}"
    cached = await _redis.get(cache_key)
    if cached:
        return RegimeClassification.model_validate_json(cached)

    result = _classify(ctx.ohlcv, ctx.current_price)
    result.pair = pair
    await _redis.set(cache_key, result.model_dump_json(), ex=300)  # 5 min TTL
    return result


# ─── Agent Voting ─────────────────────────────────────────────────────────────

def _mock_vote(intent: TradeIntent, regime: MarketRegime) -> VoteResult:
    """
    Deterministic mock voting — no LLM cost in dev.
    Encodes basic heuristics so it behaves realistically:
      • TRENDING regime → favour BUY signals
      • HIGH_VOLATILITY → sceptical, lower confidence
      • 2 agents must agree
    """
    confidence_map = {
        MarketRegime.TRENDING_UP:           (0.88, 0.82),
        MarketRegime.TRENDING_DOWN:         (0.55, 0.60),
        MarketRegime.RANGE_BOUND:           (0.72, 0.68),
        MarketRegime.HIGH_VOLATILITY_EVENT: (0.45, 0.40),
    }
    c1, c2 = confidence_map.get(regime, (0.70, 0.65))
    # Flip if sell signal
    if intent.side.value == "sell":
        c1, c2 = 1 - c1 + 0.3, 1 - c2 + 0.3
        c1, c2 = min(c1, 0.95), min(c2, 0.95)

    threshold = 0.6
    action: str = "EXECUTE" if (c1 + c2) / 2 >= threshold else "SKIP"
    return VoteResult(
        action=action,  # type: ignore[arg-type]
        confidence=round((c1 + c2) / 2, 3),
        threshold=threshold,
        votes=[
            AgentVote(agent_name="trend_agent",    action=action, confidence=c1,  # type: ignore
                      reasoning=f"regime={regime.value} side={intent.side.value}"),
            AgentVote(agent_name="momentum_agent", action=action, confidence=c2,  # type: ignore
                      reasoning=f"confidence={c2:.2f} strategy={intent.strategy_name}"),
        ],
    )


@app.post("/vote", response_model=VoteResult)
async def vote(intent: TradeIntent, ctx: StrategyContext):
    """Multi-agent voting on a TradeIntent. MODEL_PROVIDER=mock → heuristic stubs."""
    regime_key = f"trading_os:regime:{ctx.pair}"
    cached = await _redis.get(regime_key)
    regime = (RegimeClassification.model_validate_json(cached).regime
              if cached else MarketRegime.RANGE_BOUND)

    if MODEL_PROVIDER == "mock":
        return _mock_vote(intent, regime)

    if MODEL_PROVIDER == "anthropic":
        return await _anthropic_vote(intent, regime)

    if MODEL_PROVIDER == "openai":
        return await _openai_vote(intent, regime)

    raise NotImplementedError(f"Model provider '{MODEL_PROVIDER}' not supported. Use: mock | anthropic | openai")


# ─── LLM Agent Helpers ────────────────────────────────────────────────────────

def _build_agent_prompt(intent: TradeIntent, regime: MarketRegime) -> str:
    """Shared system + user prompt for all LLM voting agents."""
    return (
        "You are a risk-aware crypto trading agent. Your job is to vote EXECUTE or SKIP "
        "on a proposed trade. Be conservative — capital preservation is the top priority.\n\n"
        f"Trade Intent:\n"
        f"  strategy: {intent.strategy_name}\n"
        f"  pair:     {intent.pair}\n"
        f"  side:     {intent.side.value}\n"
        f"  quantity: {intent.quantity}\n"
        f"  price:    {intent.price}\n"
        f"  confidence: {intent.confidence}\n"
        f"  asset_class: {intent.asset_class.value}\n\n"
        f"Current Market Regime: {regime.value}\n\n"
        "Respond with a JSON object exactly like this:\n"
        '{"action": "EXECUTE", "confidence": 0.85, "reasoning": "brief reason"}\n'
        "action must be EXECUTE or SKIP. confidence must be 0.0–1.0."
    )


def _parse_agent_json(raw: str, agent_name: str) -> AgentVote:
    """Parse LLM JSON response into an AgentVote, with fallback on parse failure."""
    import re
    # Extract JSON block even if the model wraps it in ```json ... ```
    match = re.search(r'\{.*?\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return AgentVote(
                agent_name = agent_name,
                action     = data.get("action", "SKIP"),
                confidence = float(data.get("confidence", 0.5)),
                reasoning  = data.get("reasoning", ""),
            )
        except Exception:
            pass
    # Fallback: conservative SKIP on any parse failure
    return AgentVote(agent_name=agent_name, action="SKIP", confidence=0.0,
                     reasoning=f"failed to parse LLM response: {raw[:200]}")


async def _anthropic_vote(intent: TradeIntent, regime: MarketRegime) -> VoteResult:
    """Two Claude agents vote independently on the trade intent."""
    import anthropic as _anthropic
    model   = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5")
    client  = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt  = _build_agent_prompt(intent, regime)

    async def _call(agent_name: str) -> AgentVote:
        import asyncio
        resp = await asyncio.to_thread(
            lambda: client.messages.create(
                model      = model,
                max_tokens = 256,
                messages   = [{"role": "user", "content": prompt}],
            )
        )
        return _parse_agent_json(resp.content[0].text, agent_name)

    import asyncio
    a1, a2 = await asyncio.gather(_call("claude-risk-agent"), _call("claude-momentum-agent"))
    votes  = [a1, a2]
    avg_conf = sum(v.confidence for v in votes if v.action == "EXECUTE") / max(len(votes), 1)
    execute_count = sum(1 for v in votes if v.action == "EXECUTE")
    action = "EXECUTE" if execute_count > len(votes) / 2 else "SKIP"

    return VoteResult(action=action, confidence=avg_conf, votes=votes, threshold=0.6)


async def _openai_vote(intent: TradeIntent, regime: MarketRegime) -> VoteResult:
    """Two GPT-4o agents vote independently on the trade intent."""
    try:
        import openai as _openai
    except ImportError:
        raise RuntimeError("openai package not installed. Add 'openai' to requirements.txt")

    model  = os.getenv("OPENAI_MODEL", "gpt-4o")
    client = _openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = _build_agent_prompt(intent, regime)

    async def _call(agent_name: str) -> AgentVote:
        resp = await client.chat.completions.create(
            model    = model,
            messages = [{"role": "user", "content": prompt}],
            max_tokens = 256,
        )
        return _parse_agent_json(resp.choices[0].message.content or "", agent_name)

    import asyncio
    a1, a2 = await asyncio.gather(_call("gpt-risk-agent"), _call("gpt-momentum-agent"))
    votes  = [a1, a2]
    avg_conf = sum(v.confidence for v in votes if v.action == "EXECUTE") / max(len(votes), 1)
    execute_count = sum(1 for v in votes if v.action == "EXECUTE")
    action = "EXECUTE" if execute_count > len(votes) / 2 else "SKIP"

    return VoteResult(action=action, confidence=avg_conf, votes=votes, threshold=0.6)


# ─── Meta-Agent ───────────────────────────────────────────────────────────────

@app.post("/meta-agent/evaluate")
async def meta_agent_evaluate():
    """Weekly meta-agent: pull metrics from analytics, return tuning suggestions."""
    try:
        resp = await _http.get(f"{RISK_URL.replace('risk:3003', 'analytics:3006')}/strategies/metrics")
        metrics = resp.json() if resp.status_code == 200 else []
    except Exception:
        metrics = []

    recommendations = []
    for m in metrics:
        if isinstance(m, dict):
            sr = m.get("sharpe_ratio", 0)
            if sr < 0.5:
                recommendations.append({
                    "strategy": m.get("strategy_name"),
                    "action": "DISABLE",
                    "reason": f"Sharpe {sr:.2f} < 0.5",
                })
    return {"recommendations": recommendations, "evaluated_at": int(time.time() * 1000)}


# ─── Pipeline ─────────────────────────────────────────────────────────────────

@app.post("/pipeline/run")
async def run_pipeline(ctx: StrategyContext):
    """
    Full orchestration pipeline:
    1. Classify regime (cached 5 min)
    2. Call strategy service → get all enabled strategies' signals
    3. Vote on each intent
    4. POST approved intents to risk /approve
    5. Enqueue risk-approved intents to execution
    """
    results = {"intents_generated": 0, "approved": 0, "rejected": 0, "enqueued": 0, "errors": []}

    # Step 1: regime classification
    regime_result = _classify(ctx.ohlcv, ctx.current_price)
    regime_result.pair = ctx.pair
    await _redis.set(f"trading_os:regime:{ctx.pair}", regime_result.model_dump_json(), ex=300)

    # Step 2: evaluate all strategies via strategy service
    try:
        strat_resp = await _http.get(f"{STRATEGY_URL}/strategies")
        strategies = strat_resp.json() if strat_resp.status_code == 200 else []
    except Exception as e:
        results["errors"].append(f"strategy list: {e}")
        return results

    intents: list[TradeIntent] = []
    for s in strategies:
        if not s.get("enabled", True):
            continue
        try:
            eval_resp = await _http.post(
                f"{STRATEGY_URL}/strategies/{s['name']}/evaluate",
                content=ctx.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )
            if eval_resp.status_code == 200:
                data = eval_resp.json()
                # Strategy returns {"strategy":..., "fired": bool, "signal": {...}|null}
                if data and data.get("fired") and data.get("signal"):
                    intents.append(TradeIntent.model_validate(data["signal"]))
        except Exception as e:
            results["errors"].append(f"strategy eval {s['name']}: {e}")

    results["intents_generated"] = len(intents)

    # Step 3+4+5: vote → risk approve → enqueue
    for intent in intents:
        # Vote
        vote_result = _mock_vote(intent, regime_result.regime)
        if vote_result.action != "EXECUTE" or vote_result.confidence < vote_result.threshold:
            results["rejected"] += 1
            continue

        # Risk approve
        try:
            risk_resp = await _http.post(
                f"{RISK_URL}/approve",
                content=intent.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )
            if risk_resp.status_code != 200:
                results["rejected"] += 1
                continue
            approved_intent = risk_resp.json()
        except Exception as e:
            results["errors"].append(f"risk approve: {e}")
            results["rejected"] += 1
            continue

        # Enqueue
        try:
            exec_resp = await _http.post(
                f"{EXECUTION_URL}/enqueue",
                json=approved_intent,
                headers={"Content-Type": "application/json"},
            )
            if exec_resp.status_code == 200:
                results["approved"] += 1
                results["enqueued"] += 1
            else:
                results["rejected"] += 1
        except Exception as e:
            results["errors"].append(f"enqueue: {e}")
            results["rejected"] += 1

    return results


# ─── UI-friendly quick endpoints ─────────────────────────────────────────────
# These accept minimal input and build StrategyContext internally from Redis.
# They exist so the frontend never needs to supply OHLCV candle data.

class PipelineTrigger(BaseModel):
    pair: str = "BTC/USD"


class VoteSimpleRequest(BaseModel):
    pair:          str   = "BTC/USD"
    strategy_name: str   = "auto"
    side:          str   = "buy"
    quantity:      float = 0.001
    price:         float = 50000.0
    regime:        str | None = None


def _synthetic_ohlcv(price: float, n: int = 30) -> list[OHLCV]:
    """Generate n hourly OHLCV bars with small random jitter around price."""
    now_ms = int(time.time() * 1000)
    bars, current = [], price
    for i in range(n):
        jitter = current * 0.002 * (random.random() * 2 - 1)
        open_  = current
        close  = current + jitter
        high   = max(open_, close) * (1 + random.random() * 0.001)
        low    = min(open_, close) * (1 - random.random() * 0.001)
        vol    = price * 10 * (0.8 + random.random() * 0.4)
        bars.append(OHLCV(
            timestamp=now_ms - (n - i) * 3_600_000,
            open=open_, high=high, low=low, close=close, volume=vol,
        ))
        current = close
    return bars


async def _fetch_price(pair: str) -> float:
    """Read cached price from Redis (written by portfolio service)."""
    raw = await _redis.get("trading_os:price:" + pair.replace("/", "_"))
    return float(raw) if raw else 50_000.0


async def _fetch_portfolio() -> PortfolioSnapshot:
    """Read cached portfolio snapshot from Redis (written by portfolio service)."""
    raw = await _redis.get("trading_os:portfolio:snapshot")
    if raw:
        return PortfolioSnapshot.model_validate_json(raw)
    return PortfolioSnapshot(
        total_value_usd=10_000.0, daily_pnl=0.0, daily_pnl_pct=0.0,
        weekly_pnl=0.0, positions=[], portfolio_heat_pct=0.0,
    )


@app.post("/pipeline/trigger")
async def trigger_pipeline_simple(req: PipelineTrigger):
    """
    UI-friendly wrapper around /pipeline/run.
    Builds StrategyContext from Redis cache — no OHLCV required from caller.
    """
    price = await _fetch_price(req.pair)
    ctx = StrategyContext(
        pair=req.pair,
        current_price=price,
        ohlcv=_synthetic_ohlcv(price),
        portfolio_state=await _fetch_portfolio(),
        params={},
    )
    return await run_pipeline(ctx)


@app.post("/classify/quick")
async def classify_quick(pair: str = "BTC/USD"):
    """
    UI-friendly regime classification. Builds context from Redis price cache.
    """
    price = await _fetch_price(pair)
    ctx = StrategyContext(
        pair=pair,
        current_price=price,
        ohlcv=_synthetic_ohlcv(price),
        portfolio_state=await _fetch_portfolio(),
        params={},
    )
    return await classify_regime(pair, ctx)


@app.post("/vote/simple")
async def vote_simple(req: VoteSimpleRequest):
    """
    UI-friendly wrapper around /vote.
    Builds TradeIntent from simplified input; reads regime from Redis cache.
    """
    price  = req.price or await _fetch_price(req.pair)
    intent = TradeIntent(
        strategy_name=req.strategy_name,
        pair=req.pair,
        side=TradeSide(req.side.lower()),
        quantity=req.quantity,
        price=price,
        confidence=0.75,
    )
    # Read regime from Redis cache or fall back to provided value
    cached_raw = await _redis.get(f"trading_os:regime:{req.pair}")
    if cached_raw:
        regime = RegimeClassification.model_validate_json(cached_raw).regime
    else:
        try:
            regime = MarketRegime(req.regime or "RANGE_BOUND")
        except ValueError:
            regime = MarketRegime.RANGE_BOUND

    if MODEL_PROVIDER == "mock":
        return _mock_vote(intent, regime)
    if MODEL_PROVIDER == "anthropic":
        return await _anthropic_vote(intent, regime)
    return await _openai_vote(intent, regime)

