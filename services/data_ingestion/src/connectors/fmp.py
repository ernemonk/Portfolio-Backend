"""
Financial Modeling Prep API connector - Free tier available
Rate limit: 250 calls per day (free)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from .base import BaseConnector


class FinancialModelingPrepConnector(BaseConnector):
    NAME = "fmp"
    DISPLAY_NAME = "Financial Modeling Prep"
    BASE_URL = "https://financialmodelingprep.com/api/v3"
    RATE_LIMIT = 10  # requests per minute (very conservative for free tier)
    AUTH_REQUIRED = False  # Free tier available without key

    async def test_connection(self) -> Dict[str, Any]:
        try:
            # Use a truly free endpoint - profile endpoint with a major stock
            result = await self._get("/profile/AAPL")
            data = result["data"]
            
            if isinstance(data, list) and len(data) > 0:
                company_name = data[0].get("companyName", "Unknown")
                message = f"FMP API reachable (company: {company_name})"
            else:
                message = "FMP API reachable"
            
            return {
                "ok": True,
                "message": message,
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            # If profile fails, try with quote endpoint without expecting data
            try:
                result = await self._get("/quote/AAPL")
                return {
                    "ok": True,
                    "message": "FMP API reachable (quote endpoint)",
                    "response_time_ms": result["response_time_ms"],
                }
            except:
                return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current stock prices."""
        results = []
        
        for symbol in symbols:
            try:
                # Use quote endpoint for real-time price
                result = await self._get(f"/quote/{symbol.upper()}")
                data = result["data"]
                
                if not data or len(data) == 0:
                    results.append({
                        "source": self.NAME,
                        "symbol": symbol.upper(),
                        "error": "No data found"
                    })
                    continue
                
                quote = data[0]
                
                results.append({
                    "source": self.NAME,
                    "symbol": symbol.upper(),
                    "price_usd": float(quote.get("price", 0)),
                    "volume": int(quote.get("volume", 0)),
                    "change": float(quote.get("change", 0)),
                    "change_pct": float(quote.get("changesPercentage", 0)),
                    "day_high": float(quote.get("dayHigh", 0)),
                    "day_low": float(quote.get("dayLow", 0)),
                    "market_cap": quote.get("marketCap", 0),
                    "pe_ratio": quote.get("pe", 0),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
                
            except Exception as exc:
                error_msg = str(exc)
                if "429" in error_msg:
                    error_msg = "Rate limit exceeded (free tier)"
                elif "403" in error_msg:
                    error_msg = "API key required for this endpoint"
                    
                results.append({
                    "source": self.NAME,
                    "symbol": symbol,
                    "error": error_msg
                })
        
        return results

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch historical OHLC data (may require API key)."""
        try:
            # Try 1-day historical data (free tier might allow this)
            endpoint = f"/historical-price-full/{symbol.upper()}"
            params = {"serietype": "line"}
            
            if start_time and end_time:
                params["from"] = start_time.strftime("%Y-%m-%d")
                params["to"] = end_time.strftime("%Y-%m-%d")
            
            result = await self._get(endpoint, params=params)
            data = result["data"]
            
            if "historical" not in data:
                return []
            
            candles = []
            for point in data["historical"][:100]:  # Limit to 100 points
                candles.append({
                    "timestamp": point["date"],
                    "open": float(point.get("open", 0)),
                    "high": float(point.get("high", 0)),
                    "low": float(point.get("low", 0)),
                    "close": float(point.get("close", 0)),
                    "volume": int(point.get("volume", 0)),
                })
            
            return candles
            
        except Exception:
            return []  # Historical data likely requires API key

    def supported_symbols(self) -> List[str]:
        """Return list of supported symbols for this connector."""
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
            "SPY", "QQQ", "IWM", "VTI", "VOO", "SCHB", "ARKK", "XLF",
            "JPM", "BAC", "WFC", "GS", "C", "V", "MA", "PYPL", "SQ"
        ]