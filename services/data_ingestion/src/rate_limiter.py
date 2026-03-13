"""
Rate limiter with configurable per-source limits.
Uses a token-bucket algorithm backed by in-memory state (Redis optional).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RateBucket:
    """Token bucket for a single data source."""

    max_requests: int
    period_seconds: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.max_requests)
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        refill_amount = elapsed * (self.max_requests / self.period_seconds)
        self.tokens = min(self.max_requests, self.tokens + refill_amount)
        self.last_refill = now

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        while True:
            self._refill()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            # Sleep until at least one token should be available
            wait = (1.0 - self.tokens) * (self.period_seconds / self.max_requests)
            await asyncio.sleep(max(wait, 0.05))

    def update_limits(self, max_requests: int, period_seconds: float) -> None:
        """Hot-update rate limits (called when user changes config)."""
        self.max_requests = max_requests
        self.period_seconds = period_seconds


class RateLimiter:
    """Manages per-source rate-limit buckets."""

    def __init__(self) -> None:
        self._buckets: Dict[str, RateBucket] = {}

    def register(
        self, source_name: str, max_requests: int, period_seconds: float
    ) -> None:
        """Register or update a source's rate limits."""
        if source_name in self._buckets:
            self._buckets[source_name].update_limits(max_requests, period_seconds)
        else:
            self._buckets[source_name] = RateBucket(
                max_requests=max_requests, period_seconds=period_seconds
            )

    async def acquire(self, source_name: str) -> None:
        """Wait for permission to make a request to the named source."""
        bucket = self._buckets.get(source_name)
        if bucket is None:
            # No limit configured — pass through
            return
        await bucket.acquire()

    def get_status(self) -> Dict[str, dict]:
        """Return current state of all buckets (for monitoring)."""
        result = {}
        for name, bucket in self._buckets.items():
            bucket._refill()
            result[name] = {
                "max_requests": bucket.max_requests,
                "period_seconds": bucket.period_seconds,
                "tokens_remaining": round(bucket.tokens, 2),
            }
        return result
