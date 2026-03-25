"""
CoinGecko Crypto Data Provider
Free cryptocurrency market data
No API key required for free tier
"""

import httpx
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

class CoinGeckoClient:
    """
    CoinGecko API Client for crypto market data
    
    Free tier provides:
    - Real-time crypto prices
    - Historical crypto data
    - Market data
    - No API key required
    - Rate limit: 10-50 calls/minute depending on endpoint
    """
    
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    # Common crypto IDs for CoinGecko
    CRYPTO_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "AVAX": "avalanche-2",
        "DOT": "polkadot",
        "LINK": "chainlink",
        "MATIC": "matic-network",
    }
    
    def __init__(self):
        """Initialize CoinGecko client (no auth required)"""
        pass
    
    async def _request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Make async HTTP request to CoinGecko"""
        url = f"{self.BASE_URL}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
    
    # ───────────────────────────────────────────────────────────
    # Price Endpoints
    # ───────────────────────────────────────────────────────────
    
    async def get_price(
        self, 
        crypto_id: str, 
        vs_currency: str = "usd",
        include_market_cap: bool = False,
        include_24h_vol: bool = False,
        include_24h_change: bool = False
    ) -> Dict[str, Any]:
        """
        Get current price for a cryptocurrency
        
        Args:
            crypto_id: CoinGecko crypto ID (e.g., 'bitcoin', 'ethereum')
            vs_currency: Currency to compare against (e.g., 'usd', 'eur')
            include_market_cap: Include market cap data
            include_24h_vol: Include 24h volume
            include_24h_change: Include 24h price change
        
        Returns:
            {"bitcoin": {"usd": 45000.50, "market_cap": {...}, ...}}
        """
        params = {
            "ids": crypto_id,
            "vs_currencies": vs_currency,
            "include_market_cap": str(include_market_cap).lower(),
            "include_24hr_vol": str(include_24h_vol).lower(),
            "include_24hr_change": str(include_24h_change).lower(),
        }
        return await self._request("/simple/price", params)
    
    async def get_prices(
        self,
        crypto_ids: List[str],
        vs_currencies: List[str] = ["usd"],
        include_market_cap: bool = True,
        include_24h_change: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """Get prices for multiple cryptocurrencies"""
        params = {
            "ids": ",".join(crypto_ids),
            "vs_currencies": ",".join(vs_currencies),
            "include_market_cap": str(include_market_cap).lower(),
            "include_24hr_change": str(include_24h_change).lower(),
        }
        return await self._request("/simple/price", params)
    
    # ───────────────────────────────────────────────────────────
    # Market Data
    # ───────────────────────────────────────────────────────────
    
    async def get_market_data(
        self, 
        crypto_id: str, 
        vs_currency: str = "usd"
    ) -> Dict[str, Any]:
        """
        Get comprehensive market data for a cryptocurrency
        
        Returns: price, market_cap, volume, price changes, all-time highs/lows, etc.
        """
        params = {
            "vs_currency": vs_currency,
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        }
        return await self._request(f"/simple/price/{crypto_id}", params)
    
    # ───────────────────────────────────────────────────────────
    # Historical Data
    # ───────────────────────────────────────────────────────────
    
    async def get_historical_data(
        self,
        crypto_id: str,
        vs_currency: str = "usd",
        days: int = 30,
        interval: str = "daily"
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data for cryptocurrency
        
        Args:
            crypto_id: CoinGecko crypto ID
            vs_currency: Currency to compare against
            days: Number of days of history (1, 7, 30, 90, 365, max)
            interval: 'daily' for daily candles
        
        Returns:
            List of OHLCV bars
        """
        params = {
            "vs_currency": vs_currency,
            "days": days,
        }
        data = await self._request(f"/coins/{crypto_id}/market_chart", params)
        
        prices = data.get("prices", [])
        
        bars = []
        for i, price_data in enumerate(prices):
            bars.append({
                "timestamp": datetime.fromtimestamp(price_data[0] / 1000),
                "price": price_data[1],
            })
        
        return bars
    
    # ───────────────────────────────────────────────────────────
    # Trending & Discovery
    # ───────────────────────────────────────────────────────────
    
    async def get_trending(self) -> List[Dict[str, Any]]:
        """Get trending cryptocurrencies"""
        return await self._request("/search/trending")
    
    async def get_global_market_cap(self) -> Dict[str, Any]:
        """Get global cryptocurrency market data"""
        return await self._request("/global")
    
    # ───────────────────────────────────────────────────────────
    # Search & Lookup
    # ───────────────────────────────────────────────────────────
    
    async def search_crypto(self, query: str) -> List[Dict[str, str]]:
        """Search for cryptocurrencies by name or symbol"""
        params = {"query": query}
        data = await self._request("/search", params)
        return data.get("coins", [])
    
    # ───────────────────────────────────────────────────────────
    # Utilities
    # ───────────────────────────────────────────────────────────
    
    async def validate_crypto(self, crypto_id: str) -> bool:
        """Check if cryptocurrency ID is valid"""
        try:
            await self.get_price(crypto_id)
            return True
        except:
            return False
    
    def resolve_crypto_id(self, symbol: str) -> Optional[str]:
        """Resolve symbol to CoinGecko crypto ID (synchronous)"""
        return self.CRYPTO_IDS.get(symbol.upper())
    
    async def get_crypto_details(self, crypto_id: str) -> Dict[str, Any]:
        """Get comprehensive cryptocurrency details"""
        try:
            data = await self._request(f"/coins/{crypto_id}")
            return {
                "id": data.get("id"),
                "symbol": data.get("symbol"),
                "name": data.get("name"),
                "image": data.get("image", {}).get("large"),
                "market_cap_rank": data.get("market_cap_rank"),
                "description": data.get("description", {}).get("en"),
                "links": data.get("links"),
                "blockchain": data.get("platforms"),
            }
        except Exception as e:
            return {"error": str(e)}
    
    # ───────────────────────────────────────────────────────────
    # Exchanges
    # ───────────────────────────────────────────────────────────
    
    async def get_exchanges(self, per_page: int = 50) -> List[Dict[str, Any]]:
        """Get list of cryptocurrency exchanges"""
        params = {"per_page": per_page}
        return await self._request("/exchanges", params)
    
    async def get_exchange_volume(self, exchange_id: str) -> Dict[str, Any]:
        """Get trading volume for specific exchange"""
        return await self._request(f"/exchanges/{exchange_id}")
