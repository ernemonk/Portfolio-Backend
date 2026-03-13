"""
trading_os.db.database
━━━━━━━━━━━━━━━━━━━━━━
Async SQLAlchemy engine + session factory.
Every service that needs the DB imports `get_session` as a FastAPI dependency.

Usage:
    from trading_os.db.database import get_session
    from sqlalchemy.ext.asyncio import AsyncSession

    @app.get("/trades")
    async def list_trades(db: AsyncSession = Depends(get_session)):
        result = await db.execute(select(Trade))
        return result.scalars().all()
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://trading_os:trading_os_dev@localhost:5432/trading_os",
)

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("ENV") == "development",
    pool_size=10,
    max_overflow=20,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """Dev-only: create all tables without Alembic. Call on service startup."""
    from trading_os.db.models import (  # noqa: F401 — ensure models are registered
        AuditLog, RiskDecision, RiskEvent, Trade, StrategyMetrics, RegimeHistory,
        APICredential, DataSource, DataIngestionLog, MarketCandle, PriceSnapshot,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
