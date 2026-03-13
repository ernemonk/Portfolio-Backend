"""
Alpha Vantage connector — REQUIRES FREE API KEY.

Sign up at: https://www.alphavantage.co/support/#api-key
Free tier: 25 requests/day, 5 requests/minute.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import BaseConnector
from src.rate_limiter import RateLimiter


class AlphaVantageConnector(BaseConnector):
    NAME = "alpha_vantage"
    DISPLAY_NAME = "Alpha Vantage (Free Key)"
    BASE_URL = "https://www.alphavantage.co"
    REQUIRES_AUTH = True
    DEFAULT_RATE_LIMIT_REQUESTS = 5
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
        if not self.api_key:
            return {
                "ok": False,
                "message": "API key required. Get a free key at https://www.alphavantage.co/support/#api-key",
            }
        try:
            result = await self._get(
                "/query",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": "AAPL",
                    "apikey": self.api_key,
                },
            )
            data = result["data"]
            if "Error Message" in data:
                return {"ok": False, "message": data["Error Message"]}
            if "Note" in data:
                return {"ok": False, "message": f"Rate limited: {data['Note']}"}
            return {
                "ok": True,
                "message": "Alpha Vantage API reachable",
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        if not self.api_key:
            return [
                {"source": self.NAME, "symbol": s, "error": "API key required"}
                for s in symbols
            ]

        results = []
        for symbol in symbols:
            try:
                result = await self._get(
                    "/query",
                    params={
                        "function": "GLOBAL_QUOTE",
                        "symbol": symbol.upper(),
                        "apikey": self.api_key,
                    },
                )
                data = result["data"]
                if "Error Message" in data:
                    results.append(
                        {"source": self.NAME, "symbol": symbol, "error": data["Error Message"]}
                    )
                    continue
                if "Note" in data:
                    results.append(
                        {"source": self.NAME, "symbol": symbol, "error": f"Rate limited: {data['Note']}"}
                    )
                    continue

                quote = data.get("Global Quote", {})
                results.append(
                    {
                        "source": self.NAME,
                        "symbol": quote.get("01. symbol", symbol),
                        "price_usd": float(quote.get("05. price", 0)),
                        "volume_24h": float(quote.get("06. volume", 0)),
                        "change_24h_pct": float(
                            quote.get("10. change percent", "0%").rstrip("%")
                        ),
                        "open": float(quote.get("02. open", 0)),
                        "high": float(quote.get("03. high", 0)),
                        "low": float(quote.get("04. low", 0)),
                        "previous_close": float(
                            quote.get("08. previous close", 0)
                        ),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            except Exception as exc:
                results.append(
                    {"source": self.NAME, "symbol": symbol, "error": str(exc)}
                )
        return results

    async def fetch_candles(
        self, symbol: str, timeframe: str = "1d", limit: int = 100
    ) -> List[Dict[str, Any]]:
        if not self.api_key:
            return []

        # Map timeframes to Alpha Vantage functions
        if timeframe in ("1m", "5m", "15m", "30m", "1h"):
            function = "TIME_SERIES_INTRADAY"
            interval_map = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "60min"}
            params = {
                "function": function,
                "symbol": symbol.upper(),
                "interval": interval_map.get(timeframe, "60min"),
                "outputsize": "compact",
                "apikey": self.api_key,
            }
        else:
            function = "TIME_SERIES_DAILY"
            params = {
                "function": function,
                "symbol": symbol.upper(),
                "outputsize": "compact",
                "apikey": self.api_key,
            }

        result = await self._get("/query", params=params)
        data = result["data"]

        # Find the time series key
        ts_key = None
        for key in data:
            if "Time Series" in key:
                ts_key = key
                break

        if not ts_key:
            return []

        candles = []
        items = list(data[ts_key].items())[:limit]
        for date_str, values in items:
            candles.append(
                {
                    "source": self.NAME,
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": float(values.get("5. volume", 0)),
                    "candle_time": date_str,
                }
            )

        # Reverse so oldest first
        candles.reverse()
        return candles

    async def search_symbol(self, keywords: str) -> Dict[str, Any]:
        """Search for stock/ETF symbols."""
        if not self.api_key:
            return {"error": "API key required"}

        result = await self._get(
            "/query",
            params={
                "function": "SYMBOL_SEARCH",
                "keywords": keywords,
                "apikey": self.api_key,
            },
        )
        matches = result["data"].get("bestMatches", [])
        return {
            "results": [
                {
                    "symbol": m.get("1. symbol"),
                    "name": m.get("2. name"),
                    "type": m.get("3. type"),
                    "region": m.get("4. region"),
                    "currency": m.get("8. currency"),
                }
                for m in matches
            ]
        }

    def supported_symbols(self) -> List[str]:
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META",
            "JPM", "V", "JNJ", "WMT", "PG", "UNH", "HD", "DIS",
            "SPY", "QQQ", "IWM", "DIA", "VTI",
        ]
