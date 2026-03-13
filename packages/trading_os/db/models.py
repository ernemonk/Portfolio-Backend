"""
trading_os.db.models
━━━━━━━━━━━━━━━━━━━━
SQLAlchemy async ORM models — the PostgreSQL audit trail.

Tables:
  audit_log        ← every decision, reasoning, event (append-only)
  risk_decisions   ← full risk engine output per trade intent
  risk_events      ← circuit breaker triggers
  trades           ← order lifecycle (placed → filled → settled)
  strategy_metrics ← rolling PnL / win-rate per strategy
  regime_history   ← regime classification log
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trading_os.db.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class TradeStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    FAILED = "failed"


class AuditEventTypeEnum(str, enum.Enum):
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_CHECK = "RISK_CHECK"
    RISK_REJECTED = "RISK_REJECTED"
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELED = "ORDER_CANCELED"
    ORDER_FAILED = "ORDER_FAILED"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    CIRCUIT_BREAKER_TRIGGERED = "CIRCUIT_BREAKER_TRIGGERED"
    AGENT_REASONING = "AGENT_REASONING"
    REGIME_CLASSIFIED = "REGIME_CLASSIFIED"
    STRATEGY_SELECTED = "STRATEGY_SELECTED"
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    AGENT_VOTE = "AGENT_VOTE"
    REFLECTION_GENERATED = "REFLECTION_GENERATED"
    META_AGENT_EVALUATION = "META_AGENT_EVALUATION"
    PORTFOLIO_SYNCED = "PORTFOLIO_SYNCED"
    PRICE_UPDATED = "PRICE_UPDATED"


class RiskEventTypeEnum(str, enum.Enum):
    POSITION_SIZE_EXCEEDED = "POSITION_SIZE_EXCEEDED"
    STRATEGY_ALLOCATION_EXCEEDED = "STRATEGY_ALLOCATION_EXCEEDED"
    PORTFOLIO_HEAT_EXCEEDED = "PORTFOLIO_HEAT_EXCEEDED"
    DAILY_LOSS_LIMIT_BREACHED = "DAILY_LOSS_LIMIT_BREACHED"
    WEEKLY_DRAWDOWN_BREACHED = "WEEKLY_DRAWDOWN_BREACHED"
    GLOBAL_CIRCUIT_BREAKER = "GLOBAL_CIRCUIT_BREAKER"
    KILL_SWITCH_MANUAL = "KILL_SWITCH_MANUAL"
    ABNORMAL_SLIPPAGE = "ABNORMAL_SLIPPAGE"
    EXCHANGE_ERROR_SPIKE = "EXCHANGE_ERROR_SPIKE"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    BOT_HEARTBEAT_FAILED = "BOT_HEARTBEAT_FAILED"


# ─── Tables ───────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable append-only audit trail.
    Every agent reasoning, risk check, and order event is written here.
    """
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_intent_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    agent_name: Mapped[str | None] = mapped_column(String(64))
    model_used: Mapped[str | None] = mapped_column(String(64))
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class RiskDecision(Base):
    """Full risk engine output for every trade intent that entered the pipeline."""
    __tablename__ = "risk_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_intent_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    checks_performed: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Link back to the trade if one was created
    trade: Mapped[Trade | None] = relationship("Trade", back_populates="risk_decision")


class RiskEvent(Base):
    """Circuit breaker / kill-switch events (separate from per-trade decisions)."""
    __tablename__ = "risk_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-6
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    event_metadata: Mapped[dict] = mapped_column(JSONB, default={})
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Trade(Base):
    """Full order lifecycle: placed → filled → settled."""
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trade_intent_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    risk_decision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("risk_decisions.id"), index=True
    )
    strategy_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    pair: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # buy / sell
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True
    )
    exchange_order_id: Mapped[str | None] = mapped_column(String(128))
    executed_price: Mapped[float | None] = mapped_column(Float)
    filled_quantity: Mapped[float | None] = mapped_column(Float)
    fee: Mapped[float | None] = mapped_column(Float)
    pnl_usd: Mapped[float | None] = mapped_column(Float)   # profit/loss for this trade
    slippage_pct: Mapped[float | None] = mapped_column(Float)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    risk_decision: Mapped[RiskDecision | None] = relationship(
        "RiskDecision", back_populates="trade"
    )


class StrategyMetrics(Base):
    """Rolling performance metrics per strategy (updated by analytics service)."""
    __tablename__ = "strategy_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)        # pct 0-100
    total_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    avg_pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    avg_hold_time_minutes: Mapped[float | None] = mapped_column(Float)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float)
    last_trade_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RegimeHistory(Base):
    """Market regime classification log."""
    __tablename__ = "regime_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pair: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    regime: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    indicators: Mapped[dict] = mapped_column(JSONB, default={})
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


# ─── Credential & Data Ingestion Tables ──────────────────────────────────────

class CredentialTypeEnum(str, enum.Enum):
    API_KEY = "api_key"
    API_SECRET = "api_secret"
    ACCESS_TOKEN = "access_token"
    PASSWORD = "password"
    OAUTH_TOKEN = "oauth_token"
    CUSTOM = "custom"


class DataSourceStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"


class APICredential(Base):
    """
    Encrypted API credential storage.
    All sensitive values are encrypted via Fernet (AES-256) before write.
    The 'encrypted_value' column never holds plaintext.
    """
    __tablename__ = "api_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # e.g. "binance", "alpha_vantage", "coingecko"
    credential_key: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # e.g. "api_key", "api_secret"
    encrypted_value: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Fernet ciphertext
    credential_type: Mapped[str] = mapped_column(
        String(32), default="api_key"
    )
    label: Mapped[str | None] = mapped_column(
        String(128)
    )  # Human-friendly label like "Binance Main Account"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_metadata: Mapped[dict] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataSource(Base):
    """
    Configurable data source with rate limits and scheduling.
    Each row represents one API provider and its tunable parameters.
    """
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # e.g. "binance_public", "coingecko", "kraken_public"
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "crypto", "stock", "mixed"
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    # Rate limiting (user-configurable)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, default=60)
    rate_limit_period_seconds: Mapped[int] = mapped_column(Integer, default=60)
    # Scheduling
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    # State
    status: Mapped[str] = mapped_column(String(32), default="active")
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    # Config
    config: Mapped[dict] = mapped_column(JSONB, default={})
    # Supported pairs / symbols (optional filter)
    enabled_pairs: Mapped[list] = mapped_column(JSONB, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DataIngestionLog(Base):
    """Log of every data fetch attempt for monitoring & debugging."""
    __tablename__ = "data_ingestion_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # "success", "error", "rate_limited", "timeout"
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    request_metadata: Mapped[dict] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class MarketCandle(Base):
    """OHLCV candle data from any source."""
    __tablename__ = "market_candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(
        String(8), nullable=False, index=True
    )  # "1m", "5m", "1h", "1d"
    open_price: Mapped[float] = mapped_column(Float, nullable=False)
    high_price: Mapped[float] = mapped_column(Float, nullable=False)
    low_price: Mapped[float] = mapped_column(Float, nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, default=0.0)
    candle_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        # Prevent duplicate candles
        {"schema": None},
    )


class PriceSnapshot(Base):
    """Latest price snapshots (fast lookup for current prices)."""
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    volume_24h: Mapped[float | None] = mapped_column(Float)
    change_24h_pct: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    extra_data: Mapped[dict] = mapped_column(JSONB, default={})
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
