"""
Binance Public API connector — NO API KEY REQUIRED.

Docs: https://binance-docs.github.io/apidocs/spot/en/
Rate limit: 1200 requests/minute (IP-based).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import BaseConnector
from src.rate_limiter import RateLimiter

# Timeframe mapping: our format → Binance format
_TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
}


class BinanceConnector(BaseConnector):
    NAME = "binance_public"
    DISPLAY_NAME = "Binance (Public)"
    BASE_URL = "https://api.binance.com"
    REQUIRES_AUTH = False
    DEFAULT_RATE_LIMIT_REQUESTS = 1200
    DEFAULT_RATE_LIMIT_PERIOD = 60

    def __init__(
        self,
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(rate_limiter, api_key, api_secret, config)

    async def test_connection(self) -> Dict[str, Any]:
        try:
            # Try ping first, fallback to server time if geo-blocked
            try:
                result = await self._get("/api/v3/ping")
                return {
                    "ok": True,
                    "message": "Binance API reachable",
                    "response_time_ms": result["response_time_ms"],
                }
            except Exception as ping_exc:
                if "451" in str(ping_exc) or "geo" in str(ping_exc).lower():
                    # Try server time instead
                    result = await self._get("/api/v3/time")
                    return {
                        "ok": True,
                        "message": "Binance API reachable (via time endpoint)",
                        "response_time_ms": result["response_time_ms"],
                    }
                else:
                    raise ping_exc
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current prices. Symbols should be in Binance format (e.g. BTCUSDT)."""
        results = []
        for symbol in symbols:
            try:
                result = await self._get(
                    "/api/v3/ticker/24hr", params={"symbol": symbol.upper()}
                )
                data = result["data"]
                results.append(
                    {
                        "source": self.NAME,
                        "symbol": symbol.upper(),
                        "price_usd": float(data["lastPrice"]),
                        "volume_24h": float(data["volume"]),
                        "change_24h_pct": float(data["priceChangePercent"]),
                        "high_24h": float(data["highPrice"]),
                        "low_24h": float(data["lowPrice"]),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception as exc:
                error_msg = str(exc)
                if "451" in error_msg:
                    error_msg = "Geo-blocked (VPN may help)"
                elif "403" in error_msg:
                    error_msg = "Rate limited"
                results.append(
                    {"source": self.NAME, "symbol": symbol, "error": error_msg}
                )
        return results

    async def fetch_candles(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> List[Dict[str, Any]]:
        interval = _TF_MAP.get(timeframe, "1h")
        result = await self._get(
            "/api/v3/klines",
            params={
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": min(limit, 1000),
            },
        )
        candles = []
        for k in result["data"]:
            candles.append(
                {
                    "source": self.NAME,
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "candle_time": datetime.fromtimestamp(
                        k[0] / 1000, tz=timezone.utc
                    ).isoformat(),
                }
            )
        return candles

    async def get_exchange_info(self) -> Dict[str, Any]:
        """Fetch all available trading pairs."""
        result = await self._get("/api/v3/exchangeInfo")
        symbols = [
            s["symbol"]
            for s in result["data"]["symbols"]
            if s["status"] == "TRADING"
        ]
        return {"total_pairs": len(symbols), "pairs": symbols[:50]}

    def supported_symbols(self) -> List[str]:
        return [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
            "LINKUSDT", "ATOMUSDT", "LTCUSDT", "UNIUSDT", "APTUSDT",
        ]
