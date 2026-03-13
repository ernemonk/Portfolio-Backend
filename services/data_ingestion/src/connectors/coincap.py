"""
CoinCap API connector - Free crypto data
Rate limit: No explicit limit mentioned
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from .base import BaseConnector


class CoincapConnector(BaseConnector):
    NAME = "coincap"
    DISPLAY_NAME = "CoinCap"
    BASE_URL = "https://api.coincap.io/v2"
    RATE_LIMIT = 100  # requests per minute (conservative)
    AUTH_REQUIRED = False

    async def test_connection(self) -> Dict[str, Any]:
        try:
            # Test with Bitcoin data
            result = await self._get("/assets/bitcoin")
            data = result["data"]["data"]
            price = float(data["priceUsd"])
            return {
                "ok": True,
                "message": f"CoinCap API reachable (BTC=${price:,.2f})",
                "response_time_ms": result["response_time_ms"],
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current prices. Symbols can be coin IDs or symbols."""
        results = []
        
        # Get assets list first for symbol mapping
        try:
            assets_result = await self._get("/assets", params={"limit": 200})
            assets_data = assets_result["data"]["data"]
            
            # Create mapping
            symbol_to_id = {}
            for asset in assets_data:
                symbol_to_id[asset["symbol"].upper()] = asset["id"]
                symbol_to_id[asset["id"]] = asset["id"]
            
            for symbol in symbols:
                try:
                    asset_id = symbol_to_id.get(symbol.upper(), symbol.lower())
                    result = await self._get(f"/assets/{asset_id}")
                    data = result["data"]["data"]
                    
                    results.append({
                        "source": self.NAME,
                        "symbol": symbol.upper(),
                        "price_usd": float(data.get("priceUsd", 0)),
                        "volume_24h": float(data.get("volumeUsd24Hr", 0)),
                        "change_24h_pct": float(data.get("changePercent24Hr", 0)),
                        "market_cap": float(data.get("marketCapUsd", 0)),
                        "supply": float(data.get("supply", 0)),
                        "rank": int(data.get("rank", 0)),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as exc:
                    results.append({
                        "source": self.NAME,
                        "symbol": symbol,
                        "error": str(exc)
                    })
                    
        except Exception as exc:
            for symbol in symbols:
                results.append({
                    "source": self.NAME,
                    "symbol": symbol,
                    "error": f"Failed to fetch assets: {exc}"
                })
        
        return results

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """CoinCap provides history data."""
        try:
            # Map symbol to asset ID
            assets_result = await self._get("/assets", params={"search": symbol})
            assets = assets_result["data"]["data"]
            if not assets:
                return []
            
            asset_id = assets[0]["id"]
            
            params = {"interval": interval}
            if start_time:
                params["start"] = int(start_time.timestamp() * 1000)
            if end_time:
                params["end"] = int(end_time.timestamp() * 1000)
            
            result = await self._get(f"/assets/{asset_id}/history", params=params)
            history_data = result["data"]["data"]
            
            candles = []
            for point in history_data:
                candles.append({
                    "timestamp": datetime.fromtimestamp(point["time"] / 1000, timezone.utc).isoformat(),
                    "open": float(point["priceUsd"]),
                    "high": float(point["priceUsd"]),
                    "low": float(point["priceUsd"]),
                    "close": float(point["priceUsd"]),
                    "volume": 0,  # Not provided in history
                })
            
            return candles
        except Exception:
            return []

    def supported_symbols(self) -> List[str]:
        """Return list of supported symbols for this connector."""
        return [
            "bitcoin", "ethereum", "binance-coin", "solana", "ripple", 
            "tether", "cardano", "avalanche", "dogecoin", "polkadot",
            "polygon", "litecoin", "shiba-inu", "tron", "cosmos", "chainlink"
        ]