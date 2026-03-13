"""
Base class for all data connectors.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx

from src.rate_limiter import RateLimiter


class BaseConnector(ABC):
    """Abstract base for every data source connector."""

    NAME: str = ""
    DISPLAY_NAME: str = ""
    BASE_URL: str = ""
    REQUIRES_AUTH: bool = False
    # Default rate limits (overridable via config)
    DEFAULT_RATE_LIMIT_REQUESTS: int = 60
    DEFAULT_RATE_LIMIT_PERIOD: int = 60  # seconds

    def __init__(
        self,
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.rate_limiter = rate_limiter
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config or {}
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers=self._build_headers(),
        )

    def _build_headers(self) -> Dict[str, str]:
        """Override in subclass if the API needs auth headers."""
        return {"User-Agent": "TradingOS/1.0"}

    async def _get(
        self, path: str, params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Rate-limited GET request with timing."""
        await self.rate_limiter.acquire(self.NAME)
        start = time.monotonic()
        resp = await self._client.get(path, params=params)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()
        return {"data": data, "response_time_ms": elapsed_ms}

    async def close(self) -> None:
        await self._client.aclose()

    # ── Required implementations ──────────────────────────────────────────

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]:
        """Test that the API is reachable. Return {ok: bool, message: str}."""
        ...

    @abstractmethod
    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch latest prices for a list of symbols."""
        ...

    @abstractmethod
    async def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV candles for one symbol."""
        ...

    @abstractmethod
    def supported_symbols(self) -> List[str]:
        """Return a list of commonly-supported symbols."""
        ...
