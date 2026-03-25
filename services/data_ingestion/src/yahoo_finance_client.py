"""
Yahoo Finance Data Provider
Free market data for stocks and crypto
"""

import httpx
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import asyncio

class YahooFinanceClient:
    """
    Yahoo Finance API Client for market data
    
    Free tier provides:
    - Real-time/delayed stock quotes
    - Historical OHLCV data
    - Market summaries
    - No API key required
    """
    
    BASE_URL = "https://query1.finance.yahoo.com"
    
    def __init__(self):
        """Initialize Yahoo Finance client (no auth required)"""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    async def _request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make async HTTP request to Yahoo Finance"""
        url = f"{self.BASE_URL}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
    
    # ───────────────────────────────────────────────────────────
    # Quote Endpoints
    # ───────────────────────────────────────────────────────────
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get current quote for a symbol
        
        Returns: {price, change, percentChange, volume, marketCap, etc}
        """
        params = {
            "symbols": symbol,
            "fields": [
                "symbol", "longName", "regularMarketPrice", "regularMarketChange",
                "regularMarketChangePercent", "regularMarketVolume", "marketCap",
                "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "trailingPE", "dividendYield",
                "currency", "exchange"
            ]
        }
        data = await self._request("/v10/finance/quoteSummary/" + symbol, params)
        return data
    
    async def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get quotes for multiple symbols"""
        params = {
            "symbols": ",".join(symbols),
            "fields": [
                "symbol", "regularMarketPrice", "regularMarketChange",
                "regularMarketChangePercent", "regularMarketVolume"
            ]
        }
        data = await self._request("/v10/finance/quoteSummary/", params)
        return {sym: quote for sym, quote in zip(symbols, data.get("quoteResponse", {}).get("result", []))}
    
    # ───────────────────────────────────────────────────────────
    # Historical Data
    # ───────────────────────────────────────────────────────────
    
    async def get_historical_data(
        self,
        symbol: str,
        interval: str = "1d",  # 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo
        period: str = "1mo",    # 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            interval: Candle interval
            period: Time period for data
        
        Returns:
            List of OHLCV bars: [{date, open, high, low, close, volume}, ...]
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "range": period
        }
        data = await self._request("/v7/finance/chart/" + symbol, params)
        
        quotes = data.get("chart", {}).get("result", [{}])[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = data.get("chart", {}).get("result", [{}])[0].get("timestamp", [])
        
        if not quotes or not timestamps:
            return []
        
        bars = []
        for i, ts in enumerate(timestamps):
            if i >= len(quotes.get("open", [])):
                break
            
            bars.append({
                "date": datetime.fromtimestamp(ts),
                "open": quotes["open"][i],
                "high": quotes["high"][i],
                "low": quotes["low"][i],
                "close": quotes["close"][i],
                "volume": quotes["volume"][i],
            })
        
        return bars
    
    # ───────────────────────────────────────────────────────────
    # Search & Lookup
    # ───────────────────────────────────────────────────────────
    
    async def search_symbols(self, query: str) -> List[Dict[str, str]]:
        """Search for symbols by company name or ticker"""
        params = {"q": query, "quotesCount": 10}
        data = await self._request("/v1/finance/search", params)
        return data.get("quotes", [])
    
    # ───────────────────────────────────────────────────────────
    # Market Summary
    # ───────────────────────────────────────────────────────────
    
    async def get_market_summary(self) -> Dict[str, Any]:
        """Get overall market summary (indices, etc)"""
        params = {"symbols": "^GSPC,^IXIC,^DJI"}  # S&P 500, Nasdaq, Dow Jones
        data = await self._request("/v10/finance/quoteSummary/", params)
        return data.get("quoteResponse", {}).get("result", [])
    
    # ───────────────────────────────────────────────────────────
    # Utilities
    # ───────────────────────────────────────────────────────────
    
    async def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol exists and is tradeable"""
        try:
            await self.get_quote(symbol)
            return True
        except:
            return False
    
    async def get_stock_details(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive stock details"""
        try:
            data = await self._request(f"/v10/finance/quoteSummary/{symbol}")
            result = data.get("quoteSummary", {}).get("result", [{}])[0]
            return {
                "price": result.get("price", {}).get("regularMarketPrice"),
                "marketCap": result.get("summaryDetail", {}).get("marketCap"),
                "peRatio": result.get("summaryDetail", {}).get("trailingPE"),
                "dividendYield": result.get("summaryDetail", {}).get("dividendYield"),
                "fiftyTwoWeekHigh": result.get("summaryDetail", {}).get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": result.get("summaryDetail", {}).get("fiftyTwoWeekLow"),
                "sector": result.get("assetProfile", {}).get("sector"),
                "industry": result.get("assetProfile", {}).get("industry"),
                "description": result.get("assetProfile", {}).get("longBusinessSummary"),
            }
        except Exception as e:
            return {"error": str(e)}
