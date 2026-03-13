"""
YFinance Connector - The industry standard for free stock data
Used by quantitative researchers worldwide
Better than Yahoo Finance API - more reliable and feature-rich
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import yfinance as yf
import pandas as pd

from .base import BaseConnector


class YFinanceConnector(BaseConnector):
    NAME = "yfinance"
    DISPLAY_NAME = "Yahoo Finance (yfinance)"
    BASE_URL = "https://query1.finance.yahoo.com"
    RATE_LIMIT = 60  # requests per minute (conservative)
    AUTH_REQUIRED = False

    async def test_connection(self) -> Dict[str, Any]:
        try:
            def _test():
                # Test with SPY ETF (very reliable)
                ticker = yf.Ticker("SPY")
                info = ticker.fast_info
                
                if hasattr(info, 'last_price') and info.last_price:
                    price = info.last_price
                    return True, f"yfinance working (SPY=${price:.2f})"
                else:
                    # Fallback to history
                    hist = ticker.history(period="1d", interval="1d")
                    if not hist.empty:
                        price = hist['Close'].iloc[-1]
                        return True, f"yfinance working (SPY=${price:.2f} via history)"
                    return False, "No data returned"
            
            ok, message = await asyncio.to_thread(_test)
            return {"ok": ok, "message": message}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current prices using yfinance (institutional approach)"""
        
        def _fetch_batch(symbol_list):
            """Batch fetch for efficiency (hedge fund approach)"""
            results = []
            
            try:
                # Use batch download for efficiency
                if len(symbol_list) > 1:
                    tickers = yf.Tickers(' '.join(symbol_list))
                    
                    for symbol in symbol_list:
                        try:
                            ticker = tickers.tickers[symbol]
                            info = ticker.fast_info
                            
                            # Get current price
                            price = getattr(info, 'last_price', None)
                            if price is None:
                                # Fallback to history
                                hist = ticker.history(period="1d", interval="1d")
                                if not hist.empty:
                                    price = float(hist['Close'].iloc[-1])
                                else:
                                    results.append({
                                        "source": self.NAME,
                                        "symbol": symbol.upper(),
                                        "error": "No price data available"
                                    })
                                    continue
                            
                            # Get additional metrics
                            volume = getattr(info, 'regular_market_volume', 0)
                            change = getattr(info, 'regular_market_change', 0)
                            change_pct = getattr(info, 'regular_market_change_percent', 0)
                            
                            results.append({
                                "source": self.NAME,
                                "symbol": symbol.upper(),
                                "price_usd": float(price),
                                "volume": int(volume or 0),
                                "change": float(change or 0),
                                "change_pct": float(change_pct * 100 if change_pct else 0),
                                "currency": getattr(info, 'currency', 'USD'),
                                "market_cap": getattr(info, 'market_cap', 0),
                                "fetched_at": datetime.now(timezone.utc).isoformat(),
                            })
                            
                        except Exception as exc:
                            results.append({
                                "source": self.NAME,
                                "symbol": symbol.upper(),
                                "error": str(exc)
                            })
                else:
                    # Single symbol
                    symbol = symbol_list[0]
                    try:
                        ticker = yf.Ticker(symbol)
                        info = ticker.fast_info
                        
                        price = getattr(info, 'last_price', None)
                        if price is None:
                            hist = ticker.history(period="1d", interval="1d")
                            if not hist.empty:
                                price = float(hist['Close'].iloc[-1])
                            else:
                                return [{"source": self.NAME, "symbol": symbol.upper(), "error": "No data"}]
                        
                        volume = getattr(info, 'regular_market_volume', 0)
                        change = getattr(info, 'regular_market_change', 0)
                        change_pct = getattr(info, 'regular_market_change_percent', 0)
                        
                        results.append({
                            "source": self.NAME,
                            "symbol": symbol.upper(),
                            "price_usd": float(price),
                            "volume": int(volume or 0),
                            "change": float(change or 0),
                            "change_pct": float(change_pct * 100 if change_pct else 0),
                            "currency": getattr(info, 'currency', 'USD'),
                            "market_cap": getattr(info, 'market_cap', 0),
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        })
                    except Exception as exc:
                        results.append({
                            "source": self.NAME,
                            "symbol": symbol.upper(),
                            "error": str(exc)
                        })
                        
            except Exception as exc:
                # If batch fails, return errors for all symbols
                for symbol in symbol_list:
                    results.append({
                        "source": self.NAME,
                        "symbol": symbol.upper(),
                        "error": f"Batch fetch failed: {exc}"
                    })
            
            return results
        
        # Execute batch fetch in thread pool
        return await asyncio.to_thread(_fetch_batch, symbols)

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV data using yfinance"""
        
        def _fetch_history():
            try:
                ticker = yf.Ticker(symbol)
                
                # Map interval to yfinance format
                interval_map = {
                    '1m': '1m', '2m': '2m', '5m': '5m', '15m': '15m', '30m': '30m',
                    '60m': '1h', '1h': '1h', '1d': '1d', '5d': '5d', '1wk': '1wk', '1mo': '1mo'
                }
                yf_interval = interval_map.get(interval, '1d')
                
                # Determine period or use start/end dates
                if start_time and end_time:
                    hist = ticker.history(start=start_time, end=end_time, interval=yf_interval)
                else:
                    # Default to recent data
                    period_map = {
                        '1m': '1d', '2m': '1d', '5m': '5d', '15m': '5d', '30m': '1mo',
                        '1h': '1mo', '1d': '1y', '5d': '2y', '1wk': '5y', '1mo': 'max'
                    }
                    period = period_map.get(yf_interval, '1y')
                    hist = ticker.history(period=period, interval=yf_interval)
                
                if hist.empty:
                    return []
                
                candles = []
                for idx, row in hist.iterrows():
                    candles.append({
                        "timestamp": idx.strftime('%Y-%m-%dT%H:%M:%S%z') if hasattr(idx, 'strftime') else str(idx),
                        "open": float(row['Open']),
                        "high": float(row['High']),
                        "low": float(row['Low']),
                        "close": float(row['Close']),
                        "volume": int(row['Volume']),
                    })
                
                return candles[-100:]  # Limit to 100 most recent
                
            except Exception:
                return []
        
        return await asyncio.to_thread(_fetch_history)

    def supported_symbols(self) -> List[str]:
        """Return list of supported symbols for this connector."""
        return [
            # Major US Stocks
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX",
            # ETFs
            "SPY", "QQQ", "IWM", "VTI", "VOO", "SCHB", "VEA", "VWO",
            # Financial
            "JPM", "BAC", "WFC", "GS", "C", "V", "MA", "PYPL",
            # Tech
            "ORCL", "CRM", "ADBE", "INTC", "AMD", "QCOM", "TXN",
            # Crypto ETFs
            "BITO", "COIN",
            # Indices
            "^GSPC", "^IXIC", "^DJI", "^RUT",
            # Forex
            "EURUSD=X", "GBPUSD=X", "USDJPY=X",
            # Crypto (via Yahoo)
            "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD"
        ]