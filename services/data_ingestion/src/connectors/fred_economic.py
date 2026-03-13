"""
FRED Economic Data Connector
Federal Reserve Bank of St. Louis - The gold standard for macro data
Used by hedge funds for economic indicators and regime detection
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False

from .base import BaseConnector


class FREDConnector(BaseConnector):
    NAME = "fred"
    DISPLAY_NAME = "Federal Reserve Economic Data (FRED)"
    BASE_URL = "https://api.stlouisfed.org"
    RATE_LIMIT = 120  # requests per minute (FRED allows 120/min)
    AUTH_REQUIRED = False  # Free tier available

    def __init__(self, rate_limiter, api_key: Optional[str] = None, **kwargs):
        super().__init__(rate_limiter, api_key=api_key, **kwargs)
        self.api_key = api_key
        self._fred = None

    def _get_fred(self):
        """Get FRED client instance"""
        if not FRED_AVAILABLE:
            raise ImportError("fredapi not installed. Run: pip install fredapi")
        
        if self._fred is None:
            self._fred = Fred(api_key=self.api_key) if self.api_key else Fred()
        return self._fred

    async def test_connection(self) -> Dict[str, Any]:
        try:
            def _test():
                fred = self._get_fred()
                # Test with GDP data (always available)
                data = fred.get_series('GDP', limit=1)
                if data is not None and len(data) > 0:
                    latest_value = data.iloc[-1]
                    latest_date = data.index[-1].strftime('%Y-%m-%d')
                    return True, f"FRED API reachable (GDP: ${latest_value:.0f}T on {latest_date})"
                return False, "No data returned"
            
            ok, message = await asyncio.to_thread(_test)
            return {"ok": ok, "message": message}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_economic_data(self, series_ids: List[str], observation_limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch economic time series data"""
        
        def _fetch_series():
            results = []
            fred = self._get_fred()
            
            for series_id in series_ids:
                try:
                    # Get series info
                    info = fred.get_series_info(series_id)
                    data = fred.get_series(series_id, limit=observation_limit)
                    
                    if data is not None and len(data) > 0:
                        latest_value = data.iloc[-1]
                        latest_date = data.index[-1]
                        
                        # Calculate change if we have multiple observations
                        change_1m = None
                        change_1y = None
                        if len(data) >= 2:
                            prev_value = data.iloc[-2]
                            change_1m = ((latest_value - prev_value) / prev_value * 100) if prev_value != 0 else 0
                            
                            if len(data) >= 12:  # For yearly change
                                year_ago_value = data.iloc[-13]  # 12 months ago
                                change_1y = ((latest_value - year_ago_value) / year_ago_value * 100) if year_ago_value != 0 else 0
                        
                        results.append({
                            "source": self.NAME,
                            "series_id": series_id,
                            "title": info.get('title', series_id),
                            "units": info.get('units', ''),
                            "frequency": info.get('frequency', ''),
                            "latest_value": float(latest_value),
                            "latest_date": latest_date.strftime('%Y-%m-%d'),
                            "change_1m_pct": change_1m,
                            "change_1y_pct": change_1y,
                            "observations_count": len(data),
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        })
                    else:
                        results.append({
                            "source": self.NAME,
                            "series_id": series_id,
                            "error": "No data available"
                        })
                        
                except Exception as exc:
                    results.append({
                        "source": self.NAME,
                        "series_id": series_id,
                        "error": str(exc)
                    })
            
            return results
        
        return await asyncio.to_thread(_fetch_series)

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch economic indicators (treating series IDs as 'symbols')"""
        return await self.fetch_economic_data(symbols)

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch historical economic time series as 'candles'"""
        
        def _fetch_history():
            try:
                fred = self._get_fred()
                
                # Fetch series data
                if start_time and end_time:
                    data = fred.get_series(
                        symbol,
                        start=start_time.strftime('%Y-%m-%d'),
                        end=end_time.strftime('%Y-%m-%d')
                    )
                else:
                    # Default to 5 years of data
                    data = fred.get_series(symbol, limit=100)
                
                if data is None or len(data) == 0:
                    return []
                
                candles = []
                for date, value in data.items():
                    if value is not None:
                        candles.append({
                            "timestamp": date.strftime('%Y-%m-%dT00:00:00+00:00'),
                            "open": float(value),
                            "high": float(value),
                            "low": float(value),
                            "close": float(value),
                            "volume": 1,  # Not applicable to economic data
                            "series_id": symbol,
                        })
                
                return candles[-100:]  # Limit to 100 most recent
                
            except Exception:
                return []
        
        return await asyncio.to_thread(_fetch_history)

    def supported_symbols(self) -> List[str]:
        """Return list of supported economic series IDs"""
        return [
            # Core Economic Indicators
            "GDP",           # Gross Domestic Product
            "CPIAUCSL",      # Consumer Price Index
            "UNRATE",        # Unemployment Rate
            "FEDFUNDS",      # Federal Funds Rate
            "DFF",           # Daily Federal Funds Rate
            
            # Treasury Rates
            "DGS10",         # 10-Year Treasury Rate
            "DGS2",          # 2-Year Treasury Rate
            "DGS30",         # 30-Year Treasury Rate
            "T10Y2Y",        # 10-Year minus 2-Year Treasury Spread
            
            # Money Supply & Credit
            "M1SL",          # M1 Money Supply
            "M2SL",          # M2 Money Supply
            "BOGMBASE",      # Monetary Base
            
            # Labor Market
            "PAYEMS",        # Non-farm Payrolls
            "CIVPART",       # Labor Force Participation Rate
            "EMRATIO",       # Employment-Population Ratio
            
            # Production & Business
            "INDPRO",        # Industrial Production Index
            "UMCSENT",       # University of Michigan Consumer Sentiment
            "NAPMEI",        # ISM Manufacturing PMI
            
            # Housing
            "CSUSHPISA",     # Case-Shiller Home Price Index
            "HOUST",         # Housing Starts
            "PERMIT",        # Building Permits
            
            # International
            "DEXUSEU",       # USD/EUR Exchange Rate
            "DEXJPUS",       # JPY/USD Exchange Rate
            
            # Commodity Proxies
            "DCOILWTICO",    # WTI Oil Price
            "GOLDAMGBD228NLBM", # Gold Price
            
            # Market Indicators
            "VIXCLS",        # VIX Volatility Index
            "NASDAQCOM",     # NASDAQ Composite
            "SP500",         # S&P 500
        ]

    @classmethod
    def get_category_series(cls, category: str) -> List[str]:
        """Get series IDs by category for easier access"""
        categories = {
            "rates": ["FEDFUNDS", "DFF", "DGS10", "DGS2", "DGS30", "T10Y2Y"],
            "inflation": ["CPIAUCSL", "GDPDEF", "PCEPI"],
            "growth": ["GDP", "GDPC1", "INDPRO"],
            "employment": ["UNRATE", "PAYEMS", "CIVPART", "EMRATIO"],
            "sentiment": ["UMCSENT", "NAPMEI"],
            "housing": ["CSUSHPISA", "HOUST", "PERMIT"],
            "money": ["M1SL", "M2SL", "BOGMBASE"],
            "markets": ["VIXCLS", "SP500", "NASDAQCOM"],
        }
        return categories.get(category, [])