"""
IEX Cloud API connector - Free tier available
Rate limit: 100 calls per month (sandbox), 500,000 calls per month (free)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from .base import BaseConnector


class IexCloudConnector(BaseConnector):
    NAME = "iex_cloud"
    DISPLAY_NAME = "IEX Cloud"
    BASE_URL = "https://sandbox-api.iexapis.com/stable"  # Using sandbox (free)
    RATE_LIMIT = 20  # requests per minute (conservative for free tier)
    AUTH_REQUIRED = False  # Using sandbox which is free

    async def test_connection(self) -> Dict[str, Any]:
        try:
            # Test with market status
            result = await self._get("/stock/aapl/quote")
            data = result["data"]
            
            if data and "latestPrice" in data:
                price = data["latestPrice"]
                message = f"IEX Cloud API reachable (AAPL=${price})"
            else:
                message = "IEX Cloud API reachable"
            
            return {
                "ok": True,
                "message": message,
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current stock prices."""
        results = []
        
        # Try batch request first
        try:
            if len(symbols) > 1:
                symbols_str = ",".join([s.upper() for s in symbols])
                result = await self._get(f"/stock/market/batch", params={
                    "symbols": symbols_str,
                    "types": "quote",
                })
                data = result["data"]
                
                for symbol in symbols:
                    symbol_upper = symbol.upper()
                    if symbol_upper in data and "quote" in data[symbol_upper]:
                        quote = data[symbol_upper]["quote"]
                        results.append({
                            "source": self.NAME,
                            "symbol": symbol_upper,
                            "price_usd": float(quote.get("latestPrice", 0)),
                            "volume": int(quote.get("latestVolume", 0)),
                            "change": float(quote.get("change", 0)),
                            "change_pct": float(quote.get("changePercent", 0) * 100),
                            "day_high": float(quote.get("high", 0)),
                            "day_low": float(quote.get("low", 0)),
                            "market_cap": quote.get("marketCap", 0),
                            "pe_ratio": quote.get("peRatio", 0),
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        })
                    else:
                        results.append({
                            "source": self.NAME,
                            "symbol": symbol_upper,
                            "error": "Symbol not found"
                        })
                return results
                
        except Exception as batch_exc:
            # Fall back to individual requests
            pass
        
        # Individual requests fallback
        for symbol in symbols:
            try:
                result = await self._get(f"/stock/{symbol.upper()}/quote")
                data = result["data"]
                
                results.append({
                    "source": self.NAME,
                    "symbol": symbol.upper(),
                    "price_usd": float(data.get("latestPrice", 0)),
                    "volume": int(data.get("latestVolume", 0)),
                    "change": float(data.get("change", 0)),
                    "change_pct": float(data.get("changePercent", 0) * 100),
                    "day_high": float(data.get("high", 0)),
                    "day_low": float(data.get("low", 0)),
                    "market_cap": data.get("marketCap", 0),
                    "pe_ratio": data.get("peRatio", 0),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
                
            except Exception as exc:
                error_msg = str(exc)
                if "404" in error_msg:
                    error_msg = "Symbol not found"
                elif "429" in error_msg:
                    error_msg = "Rate limit exceeded"
                    
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
        """Fetch historical OHLC data."""
        try:
            # Map interval to IEX format
            if interval in ["1d", "1D"]:
                range_param = "1m"  # 1 month of daily data
            elif interval in ["1h", "1H"]:
                range_param = "1d"  # 1 day of hourly data
            else:
                range_param = "1m"
            
            result = await self._get(f"/stock/{symbol.upper()}/chart/{range_param}")
            data = result["data"]
            
            if not data:
                return []
            
            candles = []
            for point in data:
                # Handle both intraday and daily formats
                timestamp_str = point.get("datetime") or point.get("date")
                if not timestamp_str:
                    continue
                    
                candles.append({
                    "timestamp": timestamp_str,
                    "open": float(point.get("open", 0)),
                    "high": float(point.get("high", 0)),
                    "low": float(point.get("low", 0)),
                    "close": float(point.get("close", 0)),
                    "volume": int(point.get("volume", 0)),
                })
            
            return candles
            
        except Exception:
            return []

    def supported_symbols(self) -> List[str]:
        """Return list of supported symbols for this connector."""
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
            "SPY", "QQQ", "IWM", "VTI", "VOO", "SCHB", "ARKK", "XLF",
            "JPM", "BAC", "WFC", "GS", "C", "V", "MA", "PYPL", "SQ"
        ]