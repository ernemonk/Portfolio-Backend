"""
trading_os.queue.redis_queue
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis-backed implementations of ExecutionQueue, DistributedLock, RateLimiter.

Activate by setting EXECUTION_QUEUE_BACKEND=redis in docker-compose.yml.
Zero changes to business logic required — same interface as memory.py.

Why Redis beats Firestore for this:
  ✅ BRPOPLPUSH — atomic dequeue + move to processing (no message loss on crash)
  ✅ SET NX EX  — atomic lock acquire with auto-expiry (no deadlocks)
  ✅ ZADD/ZCARD — sliding-window rate limiting with atomic pipeline
  ✅ Sub-millisecond latency for all operations
  ✅ Shared state across all containers in the same Docker network
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional

import redis.asyncio as aioredis

from trading_os.queue.base import DistributedLock, ExecutionQueue, RateLimiter
from trading_os.types.models import ApprovedTradeIntent


# Redis key namespaces
_QUEUE_KEY       = "tros:exec:queue"
_PROCESSING_KEY  = "tros:exec:processing"
_LOCK_PREFIX     = "tros:lock:"
_RATE_PREFIX     = "tros:rate:"


# ─────────────────────────────────────────────────────────────────────────────
# Execution Queue
# ─────────────────────────────────────────────────────────────────────────────

class RedisExecutionQueue(ExecutionQueue):
    """
    Redis List-backed execution queue.

    Key properties:
      - LPUSH to enqueue: O(1), atomic
      - BRPOPLPUSH to dequeue: atomic move queue → processing (no message loss)
        If worker crashes after dequeue but before ack, item stays in processing.
        A separate monitor can detect stuck items and requeue them.
      - LREM to ack: remove from processing list
      - LPUSH to nack: push back to queue front for immediate retry

    Replace InMemoryExecutionQueue with this by setting:
        EXECUTION_QUEUE_BACKEND=redis
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    async def enqueue(self, intent: ApprovedTradeIntent) -> str:
        job_id  = str(uuid.uuid4())
        payload = json.dumps({"job_id": job_id, "intent": intent.model_dump()})
        await self._r.lpush(_QUEUE_KEY, payload)
        return job_id

    async def dequeue(self) -> Optional[tuple[str, ApprovedTradeIntent]]:
        # BRPOPLPUSH: pop from right of queue, push to left of processing.
        # Atomic — if we crash after this, item is in processing and can be recovered.
        raw = await self._r.brpoplpush(_QUEUE_KEY, _PROCESSING_KEY, timeout=1)
        if not raw:
            return None
        data   = json.loads(raw)
        intent = ApprovedTradeIntent(**data["intent"])
        return data["job_id"], intent

    async def ack(self, job_id: str) -> None:
        # Scan processing list for this job_id and remove it.
        # In production with high throughput, consider a HASH for O(1) lookup.
        items = await self._r.lrange(_PROCESSING_KEY, 0, -1)
        for item in items:
            data = json.loads(item)
            if data.get("job_id") == job_id:
                await self._r.lrem(_PROCESSING_KEY, 1, item)
                return

    async def nack(self, job_id: str, reason: str) -> None:
        items = await self._r.lrange(_PROCESSING_KEY, 0, -1)
        for item in items:
            data = json.loads(item)
            if data.get("job_id") == job_id:
                await self._r.lrem(_PROCESSING_KEY, 1, item)
                # TODO: increment retry counter; route to dead-letter after N retries
                await self._r.lpush(_QUEUE_KEY, item)
                return

    async def queue_depth(self) -> int:
        return await self._r.llen(_QUEUE_KEY)

    async def processing_depth(self) -> int:
        return await self._r.llen(_PROCESSING_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# Distributed Lock
# ─────────────────────────────────────────────────────────────────────────────

class RedisLock(DistributedLock):
    """
    Redis distributed lock using SET NX EX.

    Properties:
      - SET NX: only sets if key does NOT exist (atomic)
      - EX: auto-expires → prevents permanent deadlocks if worker crashes
      - Owner check on release: prevents releasing another worker's lock
        (uses a Lua script for atomic check-and-delete)

    Usage:
        async with lock.context("BTC_GRID_EXECUTE", ttl_seconds=30) as acquired:
            if not acquired:
                return  # another container has this lock
            await execute_trade(intent)
    """

    # Lua script: only delete if the value matches our owner_id.
    # Prevents a slow worker from releasing a lock that was re-acquired by another.
    _LUA_RELEASE = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    _LUA_EXTEND = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._r        = redis
        self._owner_id = str(uuid.uuid4())   # unique per container instance

    async def acquire(self, key: str, ttl_seconds: int = 30) -> bool:
        full_key = f"{_LOCK_PREFIX}{key}"
        result   = await self._r.set(
            full_key,
            self._owner_id,
            nx=True,          # only set if NOT exists
            ex=ttl_seconds,   # auto-expire to prevent deadlocks
        )
        return result is not None

    async def release(self, key: str) -> None:
        full_key = f"{_LOCK_PREFIX}{key}"
        await self._r.eval(self._LUA_RELEASE, 1, full_key, self._owner_id)

    async def extend(self, key: str, ttl_seconds: int = 30) -> bool:
        full_key = f"{_LOCK_PREFIX}{key}"
        result   = await self._r.eval(
            self._LUA_EXTEND, 1, full_key, self._owner_id, str(ttl_seconds)
        )
        return bool(result)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class RedisRateLimiter(RateLimiter):
    """
    Redis sliding-window rate limiter using sorted sets.

    Shared across all containers — if 3 workers are hitting Binance,
    the combined rate is tracked here, not per-process.

    Algorithm:
      1. ZREMRANGEBYSCORE: remove timestamps older than window
      2. ZCARD: count current requests
      3. If count < limit: ZADD current timestamp, allow request
      4. Set key TTL to auto-clean

    All 4 steps run in a pipeline (atomic enough for rate limiting purposes).
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    async def is_allowed(self, key: str, limit: int, window_seconds: int = 1) -> bool:
        full_key     = f"{_RATE_PREFIX}{key}"
        now_ms       = int(time.time() * 1000)
        window_start = now_ms - (window_seconds * 1000)

        pipe = self._r.pipeline()
        pipe.zremrangebyscore(full_key, 0, window_start)   # prune old
        pipe.zcard(full_key)                                # count remaining
        pipe.zadd(full_key, {str(now_ms): now_ms})         # add this request
        pipe.expire(full_key, window_seconds + 1)          # auto-clean
        results = await pipe.execute()

        current_count = results[1]   # count BEFORE adding current request
        return current_count < limit

    async def remaining(self, key: str, limit: int, window_seconds: int = 1) -> int:
        full_key     = f"{_RATE_PREFIX}{key}"
        now_ms       = int(time.time() * 1000)
        window_start = now_ms - (window_seconds * 1000)

        pipe = self._r.pipeline()
        pipe.zremrangebyscore(full_key, 0, window_start)
        pipe.zcard(full_key)
        results = await pipe.execute()

        return max(0, limit - results[1])


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio State Cache
# ─────────────────────────────────────────────────────────────────────────────

class RedisPortfolioCache:
    """
    Redis cache for real-time portfolio state.

    Risk checks need current positions/balances every second.
    Firestore has too much network latency for rapid risk recalculation.

    This holds:
      - Current positions (updated by portfolio service)
      - Latest balances (updated by exchange sync)
      - Live portfolio heat (updated after every trade)

    Then periodically synced to Firestore/Postgres for persistence.
    TTL ensures stale data never silently passes risk checks.
    """

    _SNAPSHOT_PREFIX = "tros:portfolio:"
    _SNAPSHOT_TTL    = 30   # seconds — risk engine refuses data older than this

    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    async def set_snapshot(self, user_id: str, snapshot: dict) -> None:
        key = f"{self._SNAPSHOT_PREFIX}{user_id}"
        await self._r.setex(key, self._SNAPSHOT_TTL, json.dumps(snapshot))

    async def get_snapshot(self, user_id: str) -> Optional[dict]:
        key = f"{self._SNAPSHOT_PREFIX}{user_id}"
        raw = await self._r.get(key)
        return json.loads(raw) if raw else None

    async def invalidate(self, user_id: str) -> None:
        await self._r.delete(f"{self._SNAPSHOT_PREFIX}{user_id}")
