"""
Kraken Public API connector — NO API KEY REQUIRED.

Docs: https://docs.kraken.com/rest/
Rate limit: ~15 requests/second for public endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import BaseConnector
from src.rate_limiter import RateLimiter

# Timeframe mapping: our format → Kraken format (minutes)
_TF_MAP = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}

# Common Kraken pair names
_SYMBOL_MAP = {
    "BTCUSDT": "XBTUSDT",
    "BTCUSD": "XXBTZUSD",
    "ETHUSDT": "ETHUSDT",
    "ETHUSD": "XETHZUSD",
    "SOLUSDT": "SOLUSDT",
    "SOLUSD": "SOLUSD",
    "XRPUSDT": "XRPUSDT",
    "ADAUSDT": "ADAUSDT",
    "DOTUSDT": "DOTUSDT",
    "LINKUSDT": "LINKUSDT",
    "AVAXUSDT": "AVAXUSDT",
    "DOGEUSDT": "XDGUSDT",
    "MATICUSDT": "MATICUSDT",
    "ATOMUSDT": "ATOMUSDT",
    "LTCUSDT": "XLTCZUSD",
}


class KrakenConnector(BaseConnector):
    NAME = "kraken_public"
    DISPLAY_NAME = "Kraken (Public)"
    BASE_URL = "https://api.kraken.com"
    REQUIRES_AUTH = False
    DEFAULT_RATE_LIMIT_REQUESTS = 15
    DEFAULT_RATE_LIMIT_PERIOD = 1

    def __init__(
        self,
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(rate_limiter, api_key, api_secret, config)

    async def _kraken_get(self, path: str, params: Optional[Dict] = None) -> Any:
        """Kraken wraps data in {error: [], result: {...}}."""
        result = await self._get(path, params=params)
        data = result["data"]
        if data.get("error") and len(data["error"]) > 0:
            raise Exception(f"Kraken API error: {data['error']}")
        return {
            "data": data.get("result", {}),
            "response_time_ms": result["response_time_ms"],
        }

    async def test_connection(self) -> Dict[str, Any]:
        try:
            result = await self._kraken_get("/0/public/SystemStatus")
            status = result["data"].get("status", "unknown")
            return {
                "ok": status == "online",
                "message": f"Kraken system status: {status}",
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        results = []
        for symbol in symbols:
            try:
                kraken_pair = _SYMBOL_MAP.get(symbol.upper(), symbol.upper())
                result = await self._kraken_get(
                    "/0/public/Ticker", params={"pair": kraken_pair}
                )
                ticker_data = result["data"]
                # Kraken returns data keyed by pair name
                for pair_key, data in ticker_data.items():
                    results.append(
                        {
                            "source": self.NAME,
                            "symbol": symbol.upper(),
                            "kraken_pair": pair_key,
                            "price_usd": float(data["c"][0]),  # last trade close
                            "volume_24h": float(data["v"][1]),  # 24h volume
                            "high_24h": float(data["h"][1]),
                            "low_24h": float(data["l"][1]),
                            "vwap_24h": float(data["p"][1]),
                            "trades_24h": int(data["t"][1]),
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
            except Exception as exc:
                results.append(
                    {"source": self.NAME, "symbol": symbol, "error": str(exc)}
                )
        return results

    async def fetch_candles(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> List[Dict[str, Any]]:
        interval = _TF_MAP.get(timeframe, 60)
        kraken_pair = _SYMBOL_MAP.get(symbol.upper(), symbol.upper())

        result = await self._kraken_get(
            "/0/public/OHLC",
            params={"pair": kraken_pair, "interval": interval},
        )

        candles = []
        # Kraken returns {pair_name: [[time, open, high, low, close, vwap, volume, count], ...]}
        for pair_key, ohlc_data in result["data"].items():
            if pair_key == "last":
                continue
            for k in ohlc_data[-limit:]:
                candles.append(
                    {
                        "source": self.NAME,
                        "symbol": symbol.upper(),
                        "timeframe": timeframe,
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[6]),
                        "candle_time": datetime.fromtimestamp(
                            int(k[0]), tz=timezone.utc
                        ).isoformat(),
                    }
                )
        return candles

    async def get_asset_pairs(self) -> Dict[str, Any]:
        """Fetch all available asset pairs."""
        result = await self._kraken_get("/0/public/AssetPairs")
        pairs = list(result["data"].keys())
        return {"total_pairs": len(pairs), "pairs": pairs[:50]}

    def supported_symbols(self) -> List[str]:
        return list(_SYMBOL_MAP.keys())
