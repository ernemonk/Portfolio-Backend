"""
Coinpaprika API connector - Free crypto data
Rate limit: 25,000 requests/month (free)
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from .base import BaseConnector


class CoinpaprikaConnector(BaseConnector):
    NAME = "coinpaprika"
    DISPLAY_NAME = "Coinpaprika"
    BASE_URL = "https://api.coinpaprika.com/v1"
    RATE_LIMIT = 50  # requests per minute (conservative)
    AUTH_REQUIRED = False

    async def test_connection(self) -> Dict[str, Any]:
        try:
            # Test with simple global stats
            result = await self._get("/global")
            data = result["data"]
            return {
                "ok": True,
                "message": f"Coinpaprika API reachable (market cap: ${data.get('market_cap_usd', 0):,.0f})",
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current prices. Symbols should be coin IDs (e.g. btc-bitcoin, eth-ethereum)."""
        results = []
        
        # Get all coins first to map symbols
        try:
            coins_result = await self._get("/coins")
            coins_data = coins_result["data"]
            
            # Create mapping from symbol to coin ID
            symbol_to_id = {}
            for coin in coins_data:
                symbol_to_id[coin["symbol"].upper()] = coin["id"]
                symbol_to_id[coin["id"]] = coin["id"]  # Allow direct ID usage
            
            for symbol in symbols:
                try:
                    coin_id = symbol_to_id.get(symbol.upper(), symbol.lower())
                    result = await self._get(f"/tickers/{coin_id}")
                    data = result["data"]
                    
                    quotes = data.get("quotes", {}).get("USD", {})
                    if not quotes:
                        results.append({
                            "source": self.NAME,
                            "symbol": symbol.upper(),
                            "error": "No USD quotes available"
                        })
                        continue
                    
                    results.append({
                        "source": self.NAME,
                        "symbol": symbol.upper(),
                        "price_usd": float(quotes.get("price", 0)),
                        "volume_24h": float(quotes.get("volume_24h", 0)),
                        "change_24h_pct": float(quotes.get("percent_change_24h", 0)),
                        "market_cap": float(quotes.get("market_cap", 0)),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as exc:
                    results.append({
                        "source": self.NAME,
                        "symbol": symbol,
                        "error": str(exc)
                    })
                    
        except Exception as exc:
            # If we can't get the coins list, return errors for all symbols
            for symbol in symbols:
                results.append({
                    "source": self.NAME,
                    "symbol": symbol,
                    "error": f"Failed to fetch coins list: {exc}"
                })
        
        return results

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Coinpaprika doesn't provide OHLC data in free tier."""
        return []

    def supported_symbols(self) -> List[str]:
        """Return list of supported symbols for this connector."""
        return [
            "btc-bitcoin", "eth-ethereum", "bnb-binance-coin", "sol-solana",
            "xrp-xrp", "usdt-tether", "ada-cardano", "avax-avalanche",
            "doge-dogecoin", "dot-polkadot", "matic-polygon", "ltc-litecoin",
            "shib-shiba-inu", "trx-tron", "atom-cosmos", "link-chainlink"
        ]