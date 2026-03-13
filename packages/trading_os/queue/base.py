"""
trading_os.queue.base
━━━━━━━━━━━━━━━━━━━━
Abstract base classes for the execution queue and distributed lock.

The key design:
  - Business logic only ever calls ExecutionQueue / DistributedLock methods.
  - The concrete implementation (memory vs redis) is injected at startup.
  - Switching from InMemoryExecutionQueue → RedisExecutionQueue requires
    exactly ONE environment variable change and zero business logic changes.

Why this matters for trading:
  Without a queue → two containers can fire the same trade simultaneously.
  Without a lock  → two workers can process the same job simultaneously.
  Both = doubled exposure. With real capital, this is catastrophic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from trading_os.types.models import ApprovedTradeIntent


# ─────────────────────────────────────────────────────────────────────────────
# Execution Queue
# ─────────────────────────────────────────────────────────────────────────────

class ExecutionQueue(ABC):
    """
    Serialized trade execution queue.

    Flow:
        Risk engine approves TradeIntent
            → enqueue(ApprovedTradeIntent)          ← orchestrator calls this
            → execution worker: dequeue()
            → place order
            → ack() on success  /  nack() on failure (retry)

    Implementations:
        InMemoryExecutionQueue  — single process, local dev (default)
        RedisExecutionQueue     — multi-container, production
    """

    @abstractmethod
    async def enqueue(self, intent: ApprovedTradeIntent) -> str:
        """
        Enqueue an approved trade intent.
        Returns a job_id for tracking.
        """
        ...

    @abstractmethod
    async def dequeue(self) -> Optional[tuple[str, ApprovedTradeIntent]]:
        """
        Dequeue the next trade intent.
        Returns (job_id, intent) or None if queue is empty.
        The item moves to a 'processing' state — not visible to other workers.
        """
        ...

    @abstractmethod
    async def ack(self, job_id: str) -> None:
        """Mark a job as successfully processed. Removes from processing state."""
        ...

    @abstractmethod
    async def nack(self, job_id: str, reason: str) -> None:
        """
        Mark a job as failed. Requeues it for retry.
        Production implementations should track retry counts + dead-letter.
        """
        ...

    @abstractmethod
    async def queue_depth(self) -> int:
        """Current number of pending (unprocessed) jobs."""
        ...

    @abstractmethod
    async def processing_depth(self) -> int:
        """Current number of jobs in 'processing' state (dequeued, not acked)."""
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Distributed Lock
# ─────────────────────────────────────────────────────────────────────────────

class DistributedLock(ABC):
    """
    Distributed lock to prevent duplicate execution.

    Example:
        async with lock.context("BTC_GRID_EXECUTE", ttl_seconds=30) as acquired:
            if not acquired:
                return  # another worker is already executing this
            await execute_trade(intent)

    Without this, scaling to 2+ containers means the same strategy can fire
    simultaneously from different instances → doubled position size.

    Implementations:
        InMemoryLock   — single process, local dev (default)
        RedisLock      — multi-container, production (uses SET NX EX)
    """

    @abstractmethod
    async def acquire(self, key: str, ttl_seconds: int = 30) -> bool:
        """
        Try to acquire lock for `key`.
        Returns True if acquired, False if already locked.
        TTL ensures lock auto-expires if the worker crashes (no deadlock).
        """
        ...

    @abstractmethod
    async def release(self, key: str) -> None:
        """Release lock. Only releases if this instance owns it."""
        ...

    @abstractmethod
    async def extend(self, key: str, ttl_seconds: int = 30) -> bool:
        """
        Extend lock TTL for long-running jobs.
        Returns True if extension successful (lock still owned by us).
        """
        ...

    def context(self, key: str, ttl_seconds: int = 30) -> "_LockContext":
        """Async context manager — preferred usage pattern."""
        return _LockContext(self, key, ttl_seconds)


class _LockContext:
    """Async context manager for DistributedLock."""

    def __init__(self, lock: DistributedLock, key: str, ttl_seconds: int):
        self._lock = lock
        self._key = key
        self._ttl = ttl_seconds
        self._acquired = False

    async def __aenter__(self) -> bool:
        self._acquired = await self._lock.acquire(self._key, self._ttl)
        return self._acquired

    async def __aexit__(self, *_) -> None:
        if self._acquired:
            await self._lock.release(self._key)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class RateLimiter(ABC):
    """
    Rate limiter to prevent exchange API bans.

    Example:
        if not await limiter.is_allowed("binance:orders", limit=10, window_seconds=1):
            await asyncio.sleep(0.1)
            return  # back off

    Implementations:
        InMemoryRateLimiter  — single process, local dev
        RedisRateLimiter     — multi-container (shared counter across instances)
    """

    @abstractmethod
    async def is_allowed(self, key: str, limit: int, window_seconds: int = 1) -> bool:
        """Returns True if request is within rate limit, False if throttled."""
        ...

    @abstractmethod
    async def remaining(self, key: str, limit: int, window_seconds: int = 1) -> int:
        """Returns number of requests remaining in the current window."""
        ...
