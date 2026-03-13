"""
Yahoo Finance connector via yfinance — NO API KEY REQUIRED.

Covers stocks, ETFs, crypto, forex, and futures.
Rate limit: ~2000 requests/hour (unofficial, IP-based).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.connectors.base import BaseConnector
from src.rate_limiter import RateLimiter

# Timeframe mapping: our format → yfinance format
_TF_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

# Period mapping for yfinance (how far back to look)
_PERIOD_MAP = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
    "1d": "max",
    "1w": "max",
    "1M": "max",
}


class YahooFinanceConnector(BaseConnector):
    NAME = "yahoo_finance"
    DISPLAY_NAME = "Yahoo Finance (Free)"
    BASE_URL = "https://query1.finance.yahoo.com"
    REQUIRES_AUTH = False
    DEFAULT_RATE_LIMIT_REQUESTS = 30
    DEFAULT_RATE_LIMIT_PERIOD = 60

    def __init__(
        self,
        rate_limiter: RateLimiter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(rate_limiter, api_key, api_secret, config)
        self._yf = None

    def _get_yf(self):
        """Lazy-load yfinance."""
        if self._yf is None:
            import yfinance as yf

            self._yf = yf
        return self._yf

    async def test_connection(self) -> Dict[str, Any]:
        try:
            yf = self._get_yf()
            # Simple test: just try to access yf module and get a basic ticker
            def _test():
                try:
                    ticker = yf.Ticker("AAPL")
                    info = ticker.info
                    if info and len(info) > 0:
                        return True, f"Yahoo Finance reachable (symbol=AAPL)"
                    else:
                        # Try with a simple history fetch
                        hist = ticker.history(period="1d")
                        if not hist.empty:
                            return True, f"Yahoo Finance reachable (history OK)"
                        return False, "No data returned"
                except Exception as e:
                    # Try with a crypto symbol instead
                    try:
                        btc = yf.Ticker("BTC-USD")
                        hist = btc.history(period="1d")
                        if not hist.empty:
                            return True, "Yahoo Finance reachable (crypto data OK)"
                        return False, str(e)
                    except:
                        return False, str(e)
            
            ok, message = await asyncio.to_thread(_test)
            return {"ok": ok, "message": message}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch current prices for stocks/crypto/ETFs.
        Accepts standard tickers: AAPL, MSFT, BTC-USD, ETH-USD, SPY, etc.
        """
        await self.rate_limiter.acquire(self.NAME)

        yf = self._get_yf()
        results = []

        def _fetch():
            tickers = yf.Tickers(" ".join(symbols))
            out = []
            for sym in symbols:
                try:
                    ticker = tickers.tickers.get(sym.upper())
                    if ticker is None:
                        out.append({"source": self.NAME, "symbol": sym, "error": "Ticker not found"})
                        continue
                    info = ticker.fast_info
                    out.append(
                        {
                            "source": self.NAME,
                            "symbol": sym.upper(),
                            "price_usd": float(info.get("lastPrice", info.get("last_price", 0))),
                            "market_cap": float(info.get("marketCap", info.get("market_cap", 0)) or 0),
                            "volume_24h": float(info.get("lastVolume", info.get("last_volume", 0)) or 0),
                            "day_high": float(info.get("dayHigh", info.get("day_high", 0)) or 0),
                            "day_low": float(info.get("dayLow", info.get("day_low", 0)) or 0),
                            "fifty_day_avg": float(info.get("fiftyDayAverage", info.get("fifty_day_average", 0)) or 0),
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                except Exception as e:
                    out.append({"source": self.NAME, "symbol": sym, "error": str(e)})
            return out

        results = await asyncio.to_thread(_fetch)
        return results

    async def fetch_candles(
        self, symbol: str, timeframe: str = "1d", limit: int = 100
    ) -> List[Dict[str, Any]]:
        await self.rate_limiter.acquire(self.NAME)

        yf = self._get_yf()
        yf_interval = _TF_MAP.get(timeframe, "1d")
        yf_period = _PERIOD_MAP.get(timeframe, "1y")

        def _fetch():
            ticker = yf.Ticker(symbol.upper())
            hist = ticker.history(period=yf_period, interval=yf_interval)
            return hist.tail(limit)

        hist = await asyncio.to_thread(_fetch)

        candles = []
        for idx, row in hist.iterrows():
            candles.append(
                {
                    "source": self.NAME,
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row["Volume"]),
                    "candle_time": idx.to_pydatetime()
                    .replace(tzinfo=timezone.utc)
                    .isoformat(),
                }
            )
        return candles

    def supported_symbols(self) -> List[str]:
        return [
            # Crypto
            "BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
            "DOGE-USD", "AVAX-USD", "DOT-USD", "LINK-USD",
            # Stocks
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META",
            # ETFs
            "SPY", "QQQ", "IWM", "DIA", "VTI",
            # Forex
            "EURUSD=X", "GBPUSD=X", "JPYUSD=X",
        ]
