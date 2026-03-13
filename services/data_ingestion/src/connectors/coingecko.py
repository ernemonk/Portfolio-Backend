"""
CoinGecko Public API connector — NO API KEY REQUIRED.

Docs: https://docs.coingecko.com/reference/introduction
Rate limit: ~30 requests/minute (IP-based, free tier).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import BaseConnector
from src.rate_limiter import RateLimiter

# Common CoinGecko IDs for top coins
_SYMBOL_TO_ID = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "UNI": "uniswap",
    "APT": "aptos",
    "NEAR": "near",
    "ARB": "arbitrum",
    "OP": "optimism",
    "SUI": "sui",
}


class CoinGeckoConnector(BaseConnector):
    NAME = "coingecko"
    DISPLAY_NAME = "CoinGecko (Free)"
    BASE_URL = "https://api.coingecko.com"
    REQUIRES_AUTH = False
    DEFAULT_RATE_LIMIT_REQUESTS = 25
    DEFAULT_RATE_LIMIT_PERIOD = 60

    def __init__(
        self,
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(rate_limiter, api_key, api_secret, config)

    def _build_headers(self) -> Dict[str, str]:
        headers = {"User-Agent": "TradingOS/1.0"}
        # If user has a CoinGecko Pro/Demo API key, include it
        if self.api_key:
            headers["x-cg-demo-api-key"] = self.api_key
        return headers

    async def test_connection(self) -> Dict[str, Any]:
        try:
            result = await self._get("/api/v3/ping")
            return {
                "ok": True,
                "message": "CoinGecko API reachable",
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current prices. Accepts ticker symbols (BTC, ETH) or CoinGecko IDs."""
        # Convert symbols to CoinGecko IDs
        ids = []
        for s in symbols:
            s_upper = s.upper()
            if s_upper in _SYMBOL_TO_ID:
                ids.append(_SYMBOL_TO_ID[s_upper])
            else:
                ids.append(s.lower())  # Assume it's already a CoinGecko ID

        ids_str = ",".join(ids)
        result = await self._get(
            "/api/v3/simple/price",
            params={
                "ids": ids_str,
                "vs_currencies": "usd",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
        )

        results = []
        data = result["data"]
        for coin_id, coin_data in data.items():
            # Find the original symbol
            symbol = coin_id
            for sym, cid in _SYMBOL_TO_ID.items():
                if cid == coin_id:
                    symbol = sym
                    break

            results.append(
                {
                    "source": self.NAME,
                    "symbol": symbol,
                    "coingecko_id": coin_id,
                    "price_usd": coin_data.get("usd", 0),
                    "volume_24h": coin_data.get("usd_24h_vol"),
                    "change_24h_pct": coin_data.get("usd_24h_change"),
                    "market_cap": coin_data.get("usd_market_cap"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return results

    async def fetch_candles(
        self, symbol: str, timeframe: str = "1d", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch OHLC data. CoinGecko free tier supports 1/7/14/30/90/180/365 day ranges."""
        # Map timeframe to days parameter
        days_map = {
            "1d": 1,
            "7d": 7,
            "14d": 14,
            "30d": 30,
            "90d": 90,
            "180d": 180,
            "1y": 365,
        }
        days = days_map.get(timeframe, 30)

        s_upper = symbol.upper()
        coin_id = _SYMBOL_TO_ID.get(s_upper, symbol.lower())

        result = await self._get(
            f"/api/v3/coins/{coin_id}/ohlc",
            params={"vs_currency": "usd", "days": str(days)},
        )

        candles = []
        for point in result["data"]:
            candles.append(
                {
                    "source": self.NAME,
                    "symbol": s_upper,
                    "timeframe": timeframe,
                    "open": point[1],
                    "high": point[2],
                    "low": point[3],
                    "close": point[4],
                    "volume": 0,  # CoinGecko OHLC doesn't include volume
                    "candle_time": datetime.fromtimestamp(
                        point[0] / 1000, tz=timezone.utc
                    ).isoformat(),
                }
            )
        return candles

    async def get_trending(self) -> Dict[str, Any]:
        """Fetch trending coins."""
        result = await self._get("/api/v3/search/trending")
        coins = []
        for item in result["data"].get("coins", []):
            coin = item.get("item", {})
            coins.append(
                {
                    "name": coin.get("name"),
                    "symbol": coin.get("symbol"),
                    "market_cap_rank": coin.get("market_cap_rank"),
                    "thumb": coin.get("thumb"),
                }
            )
        return {"trending": coins}

    def supported_symbols(self) -> List[str]:
        return list(_SYMBOL_TO_ID.keys())
