"""
trading_os.types.models
━━━━━━━━━━━━━━━━━━━━━━
Shared Pydantic contracts used by every service.

Import pattern (PYTHONPATH=/packages set in docker-compose):
    from trading_os.types.models import TradeIntent, RiskDecision

These models are the ONLY way services communicate.
Never pass raw dicts or Any across service boundaries.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class MarketRegime(str, Enum):
    TRENDING_UP           = "TRENDING_UP"
    TRENDING_DOWN         = "TRENDING_DOWN"
    RANGE_BOUND           = "RANGE_BOUND"
    HIGH_VOLATILITY_EVENT = "HIGH_VOLATILITY_EVENT"
    LOW_LIQUIDITY         = "LOW_LIQUIDITY"
    UNKNOWN               = "UNKNOWN"


class TradeSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET     = "market"
    LIMIT      = "limit"
    STOP_LIMIT = "stop_limit"


class TradeStatus(str, Enum):
    PENDING          = "pending"
    PLACED           = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED           = "filled"
    CANCELED         = "canceled"
    FAILED           = "failed"


class AuditEventType(str, Enum):
    SIGNAL_GENERATED          = "SIGNAL_GENERATED"
    RISK_CHECK                = "RISK_CHECK"
    RISK_REJECTED             = "RISK_REJECTED"
    ORDER_PLACED              = "ORDER_PLACED"
    ORDER_FILLED              = "ORDER_FILLED"
    ORDER_CANCELED            = "ORDER_CANCELED"
    ORDER_FAILED              = "ORDER_FAILED"
    KILL_SWITCH_ACTIVATED     = "KILL_SWITCH_ACTIVATED"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    AGENT_REASONING           = "AGENT_REASONING"
    REGIME_CLASSIFIED         = "REGIME_CLASSIFIED"
    STRATEGY_SELECTED         = "STRATEGY_SELECTED"
    STRATEGY_DISABLED         = "STRATEGY_DISABLED"
    AGENT_VOTE                = "AGENT_VOTE"
    REFLECTION_GENERATED      = "REFLECTION_GENERATED"
    META_AGENT_EVALUATION     = "META_AGENT_EVALUATION"
    PORTFOLIO_SYNCED          = "PORTFOLIO_SYNCED"
    PRICE_UPDATED             = "PRICE_UPDATED"


class AssetClass(str, Enum):
    """
    Asset class abstraction — strategies and risk checks use this
    instead of hardcoding crypto assumptions.  Enables equities/futures
    support without touching core logic.
    """
    CRYPTO  = "crypto"
    EQUITY  = "equity"
    FUTURES = "futures"
    FOREX   = "forex"


class TimeInForce(str, Enum):
    """
    Order time-in-force, abstracted from exchange-specific values.
    Adapters translate these to exchange-native strings.
    """
    GTC = "gtc"   # Good Till Canceled
    IOC = "ioc"   # Immediate Or Cancel
    FOK = "fok"   # Fill Or Kill
    DAY = "day"   # Day order (cancel at market close)


class PositionType(str, Enum):
    """
    Position / instrument type. Spot is the only live type in Phase 1.
    Margin, perpetual and futures are declared here so the type system
    is ready for Phase 3 without model-breaking changes.
    """
    SPOT      = "spot"
    MARGIN    = "margin"
    PERPETUAL = "perpetual"
    FUTURES   = "futures"
    OPTION    = "option"


class RiskEventType(str, Enum):
    POSITION_SIZE_EXCEEDED        = "POSITION_SIZE_EXCEEDED"        # Level 1
    STRATEGY_ALLOCATION_EXCEEDED  = "STRATEGY_ALLOCATION_EXCEEDED"  # Level 2
    PORTFOLIO_HEAT_EXCEEDED       = "PORTFOLIO_HEAT_EXCEEDED"       # Level 3
    DAILY_LOSS_LIMIT_BREACHED     = "DAILY_LOSS_LIMIT_BREACHED"     # Level 4
    WEEKLY_DRAWDOWN_BREACHED      = "WEEKLY_DRAWDOWN_BREACHED"      # Level 5
    GLOBAL_CIRCUIT_BREAKER        = "GLOBAL_CIRCUIT_BREAKER"        # Level 6
    KILL_SWITCH_MANUAL            = "KILL_SWITCH_MANUAL"            # Level 6
    ABNORMAL_SLIPPAGE             = "ABNORMAL_SLIPPAGE"             # Level 6
    EXCHANGE_ERROR_SPIKE          = "EXCHANGE_ERROR_SPIKE"          # Level 6
    VOLATILITY_SPIKE              = "VOLATILITY_SPIKE"              # Level 6
    BOT_HEARTBEAT_FAILED          = "BOT_HEARTBEAT_FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# Market Data
# ─────────────────────────────────────────────────────────────────────────────

class OHLCV(BaseModel):
    timestamp: int    # Unix ms
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float


class MarketSnapshot(BaseModel):
    pair:          str
    current_price: float
    ohlcv:         list[OHLCV]
    funding_rate:  Optional[float] = None
    timestamp:     int = Field(default_factory=lambda: int(time.time() * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio
# ─────────────────────────────────────────────────────────────────────────────

class Position(BaseModel):
    asset:           str
    quantity:        float
    value_usd:       float
    allocation_pct:  float
    unrealized_pnl:  Optional[float] = None


class PortfolioSnapshot(BaseModel):
    total_value_usd:    float
    daily_pnl:          float        # USD change from yesterday
    daily_pnl_pct:      float
    weekly_pnl:         float
    positions:          list[Position]
    portfolio_heat_pct: float        # total open risk exposure as % of portfolio
    last_updated:       int = Field(default_factory=lambda: int(time.time() * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Strategy Contracts
# ─────────────────────────────────────────────────────────────────────────────

class StrategyContext(BaseModel):
    """
    Read-only context injected into every strategy module.
    Strategy modules ONLY receive this — no DB, no exchange, no secrets.
    """
    pair:            str
    current_price:   float
    ohlcv:           list[OHLCV]
    portfolio_state: PortfolioSnapshot
    params:          dict[str, Any]
    regime:          Optional[MarketRegime] = None
    last_trade_at:   dict[str, int] = {}    # strategy_name → last trade unix ms


class TradeIntent(BaseModel):
    """
    Signal from a strategy module — pure intent, no exchange calls.
    The execution service never receives this directly.
    It only accepts ApprovedTradeIntent (risk-engine signed).

    venue: target exchange/broker key — must be registered in EXCHANGE_REGISTRY.
           "paper" (default) → simulated fill, no real orders.
           "binance" | "kraken" | "coinbase" | "alpaca" → live routing.
    """
    id:            str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_name: str
    pair:          str
    side:          TradeSide
    quantity:      float
    price:         Optional[float] = None   # None = market order
    order_type:    OrderType = OrderType.MARKET
    confidence:    Optional[float] = None   # 0–1, from agent vote
    reasoning_id:  Optional[str] = None    # links to audit_log entry

    # ── Venue + instrument abstraction (exchange-agnostic routing) ──────────
    venue:         str          = "paper"                 # EXCHANGE_REGISTRY key
    asset_class:   AssetClass   = AssetClass.CRYPTO       # crypto | equity | futures | forex
    time_in_force: TimeInForce  = TimeInForce.GTC         # gtc | ioc | fok | day
    position_type: PositionType = PositionType.SPOT       # spot | margin | perpetual | futures

    generated_at:  int = Field(default_factory=lambda: int(time.time() * 1000))


class ApprovedTradeIntent(TradeIntent):
    """
    TradeIntent that has passed every risk engine check.
    Signed internally — execution service validates this signature before acting.
    """
    risk_decision_id: str
    approved_at:      int = Field(default_factory=lambda: int(time.time() * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Risk Engine
# ─────────────────────────────────────────────────────────────────────────────

class RiskCheck(BaseModel):
    name:     str       # e.g. "POSITION_SIZE", "DAILY_LOSS", "PORTFOLIO_HEAT"
    level:    int       # 1–6 capital protection hierarchy level
    passed:   bool
    value:    float     # actual value at time of check
    limit:    float     # configured limit
    message:  Optional[str] = None


class RiskDecision(BaseModel):
    id:               str = Field(default_factory=lambda: str(uuid.uuid4()))
    trade_intent_id:  str
    approved:         bool
    rejection_reason: Optional[str] = None   # name of first failing check
    checks_performed: list[RiskCheck]
    timestamp:        int = Field(default_factory=lambda: int(time.time() * 1000))


class RiskConfig(BaseModel):
    max_position_size_pct:        float = 10.0   # max 10% of portfolio per trade
    max_strategy_allocation_pct:  float = 30.0   # max 30% allocated to one strategy
    max_portfolio_heat_pct:       float = 60.0   # total open risk cap
    daily_loss_limit_usd:         float = 500.0  # auto-pause all strategies at this loss
    weekly_drawdown_pct:          float = 10.0   # escalated alert + mandatory review
    max_leverage:                 float = 1.0    # 1 = no leverage
    close_positions_on_kill_switch: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration / Agents
# ─────────────────────────────────────────────────────────────────────────────

class AgentVote(BaseModel):
    agent_name: str
    action:     Literal["EXECUTE", "SKIP"]
    confidence: float    # 0–1
    reasoning:  str      # for audit log only — never in execution path


class VoteResult(BaseModel):
    action:     Literal["EXECUTE", "SKIP"]
    confidence: float    # consensus ratio 0–1
    votes:      list[AgentVote]
    threshold:  float = 0.6


class RegimeClassification(BaseModel):
    pair:            str
    regime:          MarketRegime
    confidence:      float
    atr:             float = 0.0
    volatility_pct:  float = 0.0
    volume_spike:    bool  = False
    trend_strength:  float = 0.0   # ADX value
    funding_rate:    Optional[float] = None
    indicators:      dict[str, Any] = {}  # raw indicator values (ADX, DI+, DI-, etc.)
    classified_at:   int = Field(default_factory=lambda: int(time.time() * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────

class OrderResult(BaseModel):
    order_id:         str
    exchange_order_id: Optional[str] = None  # None in paper mode
    status:           Literal["placed", "filled", "partial", "failed"]
    executed_price:   Optional[float] = None
    filled_quantity:  Optional[float] = None
    fee:              Optional[float] = None
    slippage_pct:     Optional[float] = None
    fill_time_ms:     Optional[int]   = None
    is_paper:         bool = True


class ExecutionQuality(BaseModel):
    order_id:       str
    intended_price: float
    executed_price: float
    slippage_pct:   float
    fill_time_ms:   int
    partial_fill:   bool
    fill_ratio:     float   # 1.0 = fully filled


# ─────────────────────────────────────────────────────────────────────────────
# Circuit Breakers
# ─────────────────────────────────────────────────────────────────────────────

class CircuitBreaker(BaseModel):
    level:      int       # 1–6
    event_type: RiskEventType
    action:     Literal[
        "PAUSE_STRATEGY",
        "PAUSE_ALL_STRATEGIES",
        "REQUIRE_MANUAL_REVIEW",
        "FULL_SYSTEM_HALT",
    ]
    metadata:   dict[str, Any] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id:              str = Field(default_factory=lambda: str(uuid.uuid4()))
    trade_intent_id: Optional[str] = None
    event_type:      AuditEventType
    agent_name:      Optional[str] = None
    model_used:      Optional[str] = None   # None for deterministic steps
    input:           dict[str, Any]
    output:          dict[str, Any]
    duration_ms:     Optional[int] = None
    created_at:      int = Field(default_factory=lambda: int(time.time() * 1000))


# ─────────────────────────────────────────────────────────────────────────────
# Health (all services expose GET /health)
# ─────────────────────────────────────────────────────────────────────────────

class HealthCheck(BaseModel):
    service:   str
    status:    Literal["ok", "degraded", "down"]
    version:   str
    uptime:    float
    checks:    dict[str, str]
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
