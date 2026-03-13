"""
trading_os.queue.memory
━━━━━━━━━━━━━━━━━━━━━━━
In-memory implementations of ExecutionQueue, DistributedLock, RateLimiter.

Use when:
  - Local development / single container
  - Unit testing
  - Initial build (start here, switch to Redis when scaling)

Switch to redis.py when:
  - Running 2+ containers
  - Need execution safety across processes
  - EXECUTION_QUEUE_BACKEND=redis in docker-compose.yml
"""

from __future__ import annotations

import time
import uuid
from collections import deque, defaultdict
from typing import Optional

from trading_os.queue.base import DistributedLock, ExecutionQueue, RateLimiter
from trading_os.types.models import ApprovedTradeIntent


# ─────────────────────────────────────────────────────────────────────────────
# Execution Queue
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryExecutionQueue(ExecutionQueue):
    """
    Single-process FIFO execution queue.

    NOT safe across multiple processes — use RedisExecutionQueue for that.
    Safe within a single process: asyncio is single-threaded so no races.
    """

    def __init__(self) -> None:
        # (job_id, intent) pairs waiting to be processed
        self._pending:    deque[tuple[str, ApprovedTradeIntent]] = deque()
        # job_id → intent for jobs currently being processed
        self._processing: dict[str, ApprovedTradeIntent] = {}

    async def enqueue(self, intent: ApprovedTradeIntent) -> str:
        job_id = str(uuid.uuid4())
        self._pending.append((job_id, intent))
        return job_id

    async def dequeue(self) -> Optional[tuple[str, ApprovedTradeIntent]]:
        if not self._pending:
            return None
        job_id, intent = self._pending.popleft()
        self._processing[job_id] = intent
        return job_id, intent

    async def ack(self, job_id: str) -> None:
        self._processing.pop(job_id, None)

    async def nack(self, job_id: str, reason: str) -> None:
        if job_id in self._processing:
            intent = self._processing.pop(job_id)
            # Requeue at front for immediate retry
            self._pending.appendleft((job_id, intent))

    async def queue_depth(self) -> int:
        return len(self._pending)

    async def processing_depth(self) -> int:
        return len(self._processing)


# ─────────────────────────────────────────────────────────────────────────────
# Distributed Lock
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryLock(DistributedLock):
    """
    Single-process lock using a dict with expiry timestamps.
    No cross-process safety — use RedisLock for multi-container.
    """

    def __init__(self) -> None:
        # key → (owner_id, expiry_timestamp)
        self._locks: dict[str, tuple[str, float]] = {}
        self._owner = str(uuid.uuid4())   # unique ID for this instance

    async def acquire(self, key: str, ttl_seconds: int = 30) -> bool:
        now = time.monotonic()
        existing = self._locks.get(key)
        if existing and existing[1] > now:
            return False    # locked by someone else (or self, and still valid)
        self._locks[key] = (self._owner, now + ttl_seconds)
        return True

    async def release(self, key: str) -> None:
        existing = self._locks.get(key)
        if existing and existing[0] == self._owner:
            del self._locks[key]

    async def extend(self, key: str, ttl_seconds: int = 30) -> bool:
        existing = self._locks.get(key)
        if existing and existing[0] == self._owner:
            self._locks[key] = (self._owner, time.monotonic() + ttl_seconds)
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryRateLimiter(RateLimiter):
    """
    Sliding-window rate limiter. Single-process only.
    Use RedisRateLimiter when running multiple containers (shared counter).
    """

    def __init__(self) -> None:
        # key → list of request timestamps (Unix ms)
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def is_allowed(self, key: str, limit: int, window_seconds: int = 1) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]
        if len(self._windows[key]) >= limit:
            return False
        self._windows[key].append(now)
        return True

    async def remaining(self, key: str, limit: int, window_seconds: int = 1) -> int:
        now = time.time()
        cutoff = now - window_seconds
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]
        return max(0, limit - len(self._windows[key]))
