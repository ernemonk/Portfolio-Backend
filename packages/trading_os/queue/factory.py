"""
trading_os.queue.factory
━━━━━━━━━━━━━━━━━━━━━━━━
Reads EXECUTION_QUEUE_BACKEND from environment and returns the right
implementation. Business logic never needs an if/else — just call this.

    from trading_os.queue.factory import make_queue, make_lock, make_rate_limiter

    queue   = await make_queue()
    lock    = await make_lock()
    limiter = await make_rate_limiter()
"""

from __future__ import annotations

import os
from typing import Optional

from trading_os.queue.base import DistributedLock, ExecutionQueue, RateLimiter
from trading_os.queue.memory import InMemoryExecutionQueue, InMemoryLock, InMemoryRateLimiter

_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            os.environ["REDIS_URL"],
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def make_queue() -> ExecutionQueue:
    backend = os.getenv("EXECUTION_QUEUE_BACKEND", "memory")
    if backend == "redis":
        from trading_os.queue.redis_queue import RedisExecutionQueue
        return RedisExecutionQueue(await _get_redis())
    return InMemoryExecutionQueue()


async def make_lock() -> DistributedLock:
    backend = os.getenv("EXECUTION_QUEUE_BACKEND", "memory")
    if backend == "redis":
        from trading_os.queue.redis_queue import RedisLock
        return RedisLock(await _get_redis())
    return InMemoryLock()


async def make_rate_limiter() -> RateLimiter:
    backend = os.getenv("EXECUTION_QUEUE_BACKEND", "memory")
    if backend == "redis":
        from trading_os.queue.redis_queue import RedisRateLimiter
        return RedisRateLimiter(await _get_redis())
    return InMemoryRateLimiter()
