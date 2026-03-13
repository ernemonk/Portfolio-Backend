"""
Portfolio Service  -  port 3001

Responsibilities:
  - Sync portfolio state from exchange (or paper account) into Redis cache
  - Expose read-only portfolio snapshots to other services
  - Fetch live prices from CoinGecko (free tier, no API key required)
  - Aggregate position data, daily PnL, and portfolio heat

Downstream consumers:
  risk service      - needs PortfolioSnapshot before every risk check
  strategy service  - reads StrategyContext (includes portfolio snapshot)
  analytics service - reads historical positions for metrics
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from trading_os.db.database import create_all_tables
from trading_os.types.models import HealthCheck, Position, PortfolioSnapshot


# Import routers
try:
    from .routes.registry import router as registry_router
except ImportError:
    registry_router = None

try:
    from .routes.proxy import router as proxy_router
except ImportError:
    proxy_router = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COINGECKO_BASE  = "https://api.coingecko.com/api/v3"
PRICE_CACHE_TTL = 300       # 5 min
SNAPSHOT_TTL    = 120       # 2 min
SYNC_INTERVAL   = 300       # 5 min background sync
PAPER_MODE      = os.getenv("PAPER_MODE", "true").lower() == "true"

PAIR_TO_GECKO: dict[str, str] = {
    "BTC/USDT":   "bitcoin",
    "ETH/USDT":   "ethereum",
    "SOL/USDT":   "solana",
    "BNB/USDT":   "binancecoin",
    "XRP/USDT":   "ripple",
    "ADA/USDT":   "cardano",
    "DOGE/USDT":  "dogecoin",
    "AVAX/USDT":  "avalanche-2",
    "DOT/USDT":   "polkadot",
    "MATIC/USDT": "matic-network",
}

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_redis: aioredis.Redis | None = None
_http:  httpx.AsyncClient | None = None
_start_time = time.time()


# ---------------------------------------------------------------------------
# CoinGecko helpers
# ---------------------------------------------------------------------------

async def fetch_prices(coin_ids: list[str]) -> dict[str, float]:
    """Fetch USD prices from CoinGecko.  Returns {coin_id: price_usd}."""
    if not coin_ids:
        return {}
    try:
        resp = await _http.get(
            f"{COINGECKO_BASE}/simple/price",
            params={"ids": ",".join(coin_ids), "vs_currencies": "usd"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {k: v.get("usd", 0.0) for k, v in data.items()}
    except Exception as exc:
        print(f"[portfolio] CoinGecko fetch failed: {exc}")
    return {}


async def get_price(pair: str) -> float:
    """Get price for a trading pair, with Redis cache (PRICE_CACHE_TTL)."""
    cache_key = "trading_os:price:" + pair.replace("/", "_")
    cached = await _redis.get(cache_key)
    if cached:
        return float(cached)
    gecko_id = PAIR_TO_GECKO.get(pair)
    if not gecko_id:
        return 0.0
    prices = await fetch_prices([gecko_id])
    price = prices.get(gecko_id, 0.0)
    if price > 0:
        await _redis.set(cache_key, str(price), ex=PRICE_CACHE_TTL)
    return price


# ---------------------------------------------------------------------------
# Paper portfolio
# ---------------------------------------------------------------------------

PAPER_POSITIONS: list[dict[str, Any]] = [
    {"asset": "BTC",  "quantity": 0.1,    "pair": "BTC/USDT"},
    {"asset": "ETH",  "quantity": 1.5,    "pair": "ETH/USDT"},
    {"asset": "SOL",  "quantity": 10.0,   "pair": "SOL/USDT"},
    {"asset": "USDT", "quantity": 5000.0, "pair": None},
]


async def build_paper_snapshot() -> PortfolioSnapshot:
    """Build a PortfolioSnapshot from paper positions using live CoinGecko prices."""
    pairs      = [p["pair"] for p in PAPER_POSITIONS if p["pair"]]
    gecko_ids  = [PAIR_TO_GECKO[p] for p in pairs if p in PAIR_TO_GECKO]
    prices     = await fetch_prices(gecko_ids) if gecko_ids else {}

    pair_prices: dict[str, float] = {}
    for pair in pairs:
        gid = PAIR_TO_GECKO.get(pair)
        pair_prices[pair] = prices.get(gid, 0.0) if gid else 0.0

    positions: list[Position] = []
    total_value = 0.0
    for pos in PAPER_POSITIONS:
        if pos["pair"]:
            value = pos["quantity"] * pair_prices.get(pos["pair"], 0.0)
        else:
            value = pos["quantity"]
        total_value += value
        positions.append(Position(
            asset=pos["asset"],
            quantity=pos["quantity"],
            value_usd=round(value, 2),
            allocation_pct=0.0,
        ))

    total_value = max(total_value, 1.0)
    for p in positions:
        p.allocation_pct = round(p.value_usd / total_value * 100, 2)

    heat = sum(p.allocation_pct for p in positions if p.asset != "USDT")

    return PortfolioSnapshot(
        total_value_usd=round(total_value, 2),
        daily_pnl=0.0,
        daily_pnl_pct=0.0,
        weekly_pnl=0.0,
        positions=positions,
        portfolio_heat_pct=round(heat, 2),
    )


# ---------------------------------------------------------------------------
# Background sync worker
# ---------------------------------------------------------------------------

async def _sync_worker() -> None:
    """Refresh portfolio snapshot in Redis every SYNC_INTERVAL seconds."""
    while True:
        try:
            snapshot = await build_paper_snapshot()
            await _redis.set(
                "trading_os:portfolio:snapshot",
                snapshot.model_dump_json(),
                ex=SNAPSHOT_TTL * 4,
            )
            print(
                f"[portfolio] synced: ${snapshot.total_value_usd:,.2f}  "
                f"{len(snapshot.positions)} positions  "
                f"heat={snapshot.portfolio_heat_pct:.1f}%"
            )
        except Exception as exc:
            print(f"[portfolio] sync worker error: {exc}")
        await asyncio.sleep(SYNC_INTERVAL)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _http
    _redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    _http  = httpx.AsyncClient()
    await create_all_tables()

    # Immediate sync so snapshot is available before first health check
    try:
        snapshot = await build_paper_snapshot()
        await _redis.set(
            "trading_os:portfolio:snapshot",
            snapshot.model_dump_json(),
            ex=SNAPSHOT_TTL * 4,
        )
        print(f"[portfolio] initial sync done - ${snapshot.total_value_usd:,.2f}")
    except Exception as exc:
        print(f"[portfolio] initial sync failed: {exc}")

    asyncio.create_task(_sync_worker())
    yield
    await _redis.aclose()
    await _http.aclose()


app = FastAPI(title="portfolio-service", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
if registry_router:
    app.include_router(registry_router)
if proxy_router:
    app.include_router(proxy_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthCheck)
async def health():
    checks: dict[str, str] = {}
    try:
        await _redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    snapshot_raw = await _redis.get("trading_os:portfolio:snapshot")
    checks["snapshot"] = "ok" if snapshot_raw else "missing"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthCheck(
        service="portfolio",
        status=status,
        version="0.2.0",
        uptime=round(time.time() - _start_time, 1),
        checks=checks,
        timestamp=int(time.time() * 1000),
    )


# ---------------------------------------------------------------------------
# Snapshot endpoints
# ---------------------------------------------------------------------------

@app.get("/snapshot", response_model=PortfolioSnapshot)
async def get_snapshot():
    """Return current portfolio snapshot from Redis cache."""
    raw = await _redis.get("trading_os:portfolio:snapshot")
    if not raw:
        raise HTTPException(status_code=503, detail="Snapshot not yet populated")
    return PortfolioSnapshot.model_validate_json(raw)


@app.post("/snapshot")
async def upsert_snapshot(snapshot: PortfolioSnapshot):
    """Upsert a portfolio snapshot into Redis cache."""
    await _redis.set(
        "trading_os:portfolio:snapshot",
        snapshot.model_dump_json(),
        ex=SNAPSHOT_TTL,
    )
    return {"ok": True}


@app.post("/sync")
async def trigger_sync():
    """Manually trigger a CoinGecko sync and refresh the Redis snapshot."""
    snapshot = await build_paper_snapshot()
    await _redis.set(
        "trading_os:portfolio:snapshot",
        snapshot.model_dump_json(),
        ex=SNAPSHOT_TTL * 4,
    )
    return {
        "ok": True,
        "total_value_usd": snapshot.total_value_usd,
        "positions": len(snapshot.positions),
    }


# ---------------------------------------------------------------------------
# Price / position / PnL endpoints
# ---------------------------------------------------------------------------

@app.get("/price/{pair:path}")
async def get_pair_price(pair: str):
    """Get live price for a trading pair (e.g. BTC/USDT).  Cached 5 min."""
    price = await get_price(pair.upper())
    if price == 0.0:
        raise HTTPException(status_code=404, detail=f"Price not available for {pair}")
    return {"pair": pair.upper(), "price_usd": price}


@app.get("/positions")
async def get_positions():
    """Return current open positions from the cached snapshot."""
    raw = await _redis.get("trading_os:portfolio:snapshot")
    if not raw:
        return []
    snap = PortfolioSnapshot.model_validate_json(raw)
    return snap.positions


@app.get("/pnl")
async def get_pnl():
    """Return rolling PnL metrics from the cached snapshot."""
    raw = await _redis.get("trading_os:portfolio:snapshot")
    if not raw:
        return {"daily": 0.0, "weekly": 0.0, "monthly": 0.0}
    snap = PortfolioSnapshot.model_validate_json(raw)
    return {
        "daily":     snap.daily_pnl,
        "daily_pct": snap.daily_pnl_pct,
        "weekly":    snap.weekly_pnl,
    }
