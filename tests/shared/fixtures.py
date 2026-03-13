"""
Shared test fixtures, base URLs, and reusable payloads.

All service tests import from here so payload shapes are defined in one place.
If a Pydantic model changes, fixing it here fixes every test.
"""

BASE_URL = {
    "portfolio":    "http://localhost:3001",
    "strategy":     "http://localhost:3002",
    "risk":         "http://localhost:3003",
    "execution":    "http://localhost:3004",
    "orchestrator": "http://localhost:3005",
    "analytics":    "http://localhost:3006",
    "config":       "http://localhost:3007",      # NEW: Config service
    "local_ai":     "http://localhost:3008",      # NEW: Local AI service
}

# ---------------------------------------------------------------------------
# OHLCV candles
# ---------------------------------------------------------------------------

# Minimal 3-candle set — enough for DCA / single strategy evaluate
CANDLES_3 = [
    {"timestamp": 1700000000000, "open": 29000, "high": 30000, "low": 28500, "close": 29800, "volume": 100},
    {"timestamp": 1700086400000, "open": 29800, "high": 31000, "low": 29000, "close": 30500, "volume": 120},
    {"timestamp": 1700172800000, "open": 30500, "high": 32000, "low": 30000, "close": 31500, "volume": 110},
]

# 14-candle set — enough for ADX period (regime classifier min = 14+1)
CANDLES_14 = CANDLES_3 + [
    {"timestamp": 1700259200000, "open": 31500, "high": 33000, "low": 31000, "close": 32500, "volume": 130},
    {"timestamp": 1700345600000, "open": 32500, "high": 34000, "low": 32000, "close": 33200, "volume": 115},
    {"timestamp": 1700432000000, "open": 33200, "high": 34500, "low": 32500, "close": 33800, "volume": 125},
    {"timestamp": 1700518400000, "open": 33800, "high": 35000, "low": 33000, "close": 34500, "volume": 140},
    {"timestamp": 1700604800000, "open": 34500, "high": 36000, "low": 34000, "close": 35200, "volume": 135},
    {"timestamp": 1700691200000, "open": 35200, "high": 37000, "low": 35000, "close": 36000, "volume": 150},
    {"timestamp": 1700777600000, "open": 36000, "high": 37500, "low": 35500, "close": 36800, "volume": 145},
    {"timestamp": 1700864000000, "open": 36800, "high": 38000, "low": 36500, "close": 37500, "volume": 160},
]

# 30-candle set — enough for full ADX/ATR regime classification (requires >= 30)
CANDLES_30 = CANDLES_14 + [
    {"timestamp": 1700950400000, "open": 37500, "high": 39000, "low": 37000, "close": 38200, "volume": 155},
    {"timestamp": 1701036800000, "open": 38200, "high": 40000, "low": 38000, "close": 39000, "volume": 170},
    {"timestamp": 1701123200000, "open": 39000, "high": 41000, "low": 38500, "close": 40000, "volume": 165},
    {"timestamp": 1701209600000, "open": 40000, "high": 42000, "low": 39500, "close": 41200, "volume": 180},
    {"timestamp": 1701296000000, "open": 41200, "high": 43000, "low": 41000, "close": 42000, "volume": 175},
    {"timestamp": 1701382400000, "open": 42000, "high": 43500, "low": 41500, "close": 42800, "volume": 160},
    {"timestamp": 1701468800000, "open": 42800, "high": 44000, "low": 42000, "close": 43500, "volume": 190},
    {"timestamp": 1701555200000, "open": 43500, "high": 45000, "low": 43000, "close": 44200, "volume": 200},
    {"timestamp": 1701641600000, "open": 44200, "high": 46000, "low": 44000, "close": 45000, "volume": 210},
    {"timestamp": 1701728000000, "open": 45000, "high": 46500, "low": 44500, "close": 45800, "volume": 195},
    {"timestamp": 1701814400000, "open": 45800, "high": 47000, "low": 45500, "close": 46500, "volume": 205},
    {"timestamp": 1701900800000, "open": 46500, "high": 48000, "low": 46000, "close": 47200, "volume": 220},
    {"timestamp": 1701987200000, "open": 47200, "high": 49000, "low": 47000, "close": 48000, "volume": 215},
    {"timestamp": 1702073600000, "open": 48000, "high": 50000, "low": 47500, "close": 49000, "volume": 230},
    {"timestamp": 1702160000000, "open": 49000, "high": 51000, "low": 48500, "close": 50000, "volume": 240},
    {"timestamp": 1702246400000, "open": 50000, "high": 52000, "low": 49500, "close": 51000, "volume": 235},
]

# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

EMPTY_SNAPSHOT = {
    "total_value_usd": 10000.0,
    "daily_pnl": 0.0,
    "daily_pnl_pct": 0.0,
    "weekly_pnl": 0.0,
    "positions": [],
    "portfolio_heat_pct": 0.0,
}

SNAPSHOT_WITH_BTC = {
    "total_value_usd": 10000.0,
    "daily_pnl": 0.0,
    "daily_pnl_pct": 0.0,
    "weekly_pnl": 0.0,
    "positions": [
        {"asset": "BTC", "quantity": 0.01, "value_usd": 300.0, "allocation_pct": 3.0}
    ],
    "portfolio_heat_pct": 3.0,
}

# ---------------------------------------------------------------------------
# StrategyContext  (used by strategy/evaluate, orchestrator/vote, pipeline/run)
# ---------------------------------------------------------------------------

STRATEGY_CTX = {
    "pair":            "BTC/USDT",
    "current_price":   30000.0,
    "ohlcv":           CANDLES_3,
    "portfolio_state": EMPTY_SNAPSHOT,
    "params":          {"interval_hours": 1, "amount_usd": 100},
}

STRATEGY_CTX_30 = {**STRATEGY_CTX, "ohlcv": CANDLES_30}

# ---------------------------------------------------------------------------
# TradeIntent  (plain, not yet risk-approved)
# ---------------------------------------------------------------------------

INTENT_SMALL = {
    "strategy_name": "dca",
    "pair":          "BTC/USDT",
    "side":          "buy",
    "quantity":      0.01,    # $300 = 3% of $10k portfolio — should pass L1
    "price":         30000,
    "order_type":    "market",
    "confidence":    0.8,
}

INTENT_OVERSIZED = {
    **INTENT_SMALL,
    "quantity": 10,           # $300 000 = 3 000% of portfolio — must fail L1
}

# ---------------------------------------------------------------------------
# ApprovedTradeIntent  (execution /enqueue needs risk_decision_id)
# ---------------------------------------------------------------------------

APPROVED_INTENT = {
    **INTENT_SMALL,
    "quantity":          0.001,
    "risk_decision_id":  "test-risk-decision-0001",
}

# ---------------------------------------------------------------------------
# Orchestrator  —  vote body
# FastAPI merges two Pydantic params into a single JSON object
# ---------------------------------------------------------------------------

VOTE_BODY = {
    "intent": INTENT_SMALL,
    "ctx":    STRATEGY_CTX,
}

# ---------------------------------------------------------------------------
# Backtest request  (BacktestRequest uses `ohlcv`, not `candles`)
# ---------------------------------------------------------------------------

BACKTEST_DCA = {
    "strategy_name": "dca",
    "pair":          "BTC/USDT",
    "ohlcv":         CANDLES_3,
    "params":        {"interval_hours": 24, "amount_usd": 100},
}
