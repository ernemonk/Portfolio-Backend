"""
Alpaca Trading API Client
Handles order placement, position management, and account operations
"""

import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import asyncio

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"  # Good till cancelled
    OPQ = "opq"  # Opening
    CLS = "cls"  # Closing

class AlpacaClient:
    """
    Official Alpaca Trading API client
    
    Credentials format:
    - api_key: Your API key from Alpaca
    - api_secret: Your API secret from Alpaca
    - base_url: https://paper-api.alpaca.markets (paper trading) or 
                https://api.alpaca.markets (live trading)
    """
    
    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    LIVE_BASE_URL = "https://api.alpaca.markets"
    
    def __init__(self, api_key: str, api_secret: str, paper: bool = True):
        """
        Initialize Alpaca client
        
        Args:
            api_key: Alpaca API key
            api_secret: Alpaca API secret  
            paper: Use paper trading (True) or live trading (False)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.PAPER_BASE_URL if paper else self.LIVE_BASE_URL
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "Content-Type": "application/json"
        }
    
    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Make async HTTP request to Alpaca API"""
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, 
                url, 
                headers=self.headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
    
    # ───────────────────────────────────────────────────────────
    # Account Endpoints
    # ───────────────────────────────────────────────────────────
    
    async def get_account(self) -> Dict[str, Any]:
        """Get account details (buying power, cash, equity, etc.)"""
        return await self._request("GET", "/v2/account")
    
    async def get_account_equity(self) -> float:
        """Get current account equity"""
        account = await self.get_account()
        return float(account.get("equity", 0))
    
    async def get_buying_power(self) -> float:
        """Get available buying power"""
        account = await self.get_account()
        return float(account.get("buying_power", 0))
    
    async def get_cash(self) -> float:
        """Get available cash balance"""
        account = await self.get_account()
        return float(account.get("cash", 0))
    
    # ───────────────────────────────────────────────────────────
    # Position Endpoints
    # ───────────────────────────────────────────────────────────
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions"""
        return await self._request("GET", "/v2/positions")
    
    async def get_position(self, symbol: str) -> Dict[str, Any]:
        """Get position for specific symbol"""
        return await self._request("GET", f"/v2/positions/{symbol}")
    
    async def close_position(self, symbol: str, qty: Optional[float] = None) -> Dict[str, Any]:
        """Close a position (or reduce by qty)"""
        params = {}
        if qty:
            params["qty"] = qty
        return await self._request("DELETE", f"/v2/positions/{symbol}", params=params)
    
    # ───────────────────────────────────────────────────────────
    # Order Endpoints
    # ───────────────────────────────────────────────────────────
    
    async def place_order(
        self,
        symbol: str,
        qty: Optional[float] = None,
        notional: Optional[float] = None,
        side: OrderSide = OrderSide.BUY,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        trail_price: Optional[float] = None,
        trail_percent: Optional[float] = None,
        extended_hours: bool = False,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Place an order on Alpaca
        
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            qty: Quantity to trade (use qty or notional, not both)
            notional: Dollar amount to trade with (use qty or notional, not both)
            side: BUY or SELL
            order_type: MARKET, LIMIT, STOP, STOP_LIMIT
            time_in_force: DAY, GTC, OPQ, CLS
            limit_price: Required for LIMIT and STOP_LIMIT orders
            stop_price: Required for STOP and STOP_LIMIT orders
            trail_price: For trailing stop orders
            trail_percent: For trailing stop orders (%)
            extended_hours: Trade in extended hours
            client_order_id: Custom order ID for tracking
        
        Returns:
            Order confirmation with order_id
        """
        json_data = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "time_in_force": time_in_force.value,
        }
        
        if qty is not None:
            json_data["qty"] = qty
        elif notional is not None:
            json_data["notional"] = notional
        else:
            raise ValueError("Either qty or notional must be specified")
        
        if limit_price:
            json_data["limit_price"] = limit_price
        if stop_price:
            json_data["stop_price"] = stop_price
        if trail_price:
            json_data["trail_price"] = trail_price
        if trail_percent:
            json_data["trail_percent"] = trail_percent
        if extended_hours:
            json_data["extended_hours"] = True
        if client_order_id:
            json_data["client_order_id"] = client_order_id
        
        return await self._request("POST", "/v2/orders", json=json_data)
    
    async def get_orders(self, status: str = "all", limit: int = 100) -> List[Dict[str, Any]]:
        """Get orders with optional filtering"""
        params = {"status": status, "limit": limit}
        return await self._request("GET", "/v2/orders", params=params)
    
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get specific order details"""
        return await self._request("GET", f"/v2/orders/{order_id}")
    
    async def cancel_order(self, order_id: str) -> None:
        """Cancel an open order"""
        await self._request("DELETE", f"/v2/orders/{order_id}")
    
    async def cancel_all_orders(self) -> List[Dict[str, Any]]:
        """Cancel all open orders"""
        return await self._request("DELETE", "/v2/orders")
    
    # ───────────────────────────────────────────────────────────
    # Asset Endpoints
    # ───────────────────────────────────────────────────────────
    
    async def get_assets(self, asset_class: str = "us_equity") -> List[Dict[str, Any]]:
        """Get all tradeable assets"""
        params = {"asset_class": asset_class}
        return await self._request("GET", "/v2/assets", params=params)
    
    async def get_asset(self, symbol: str) -> Dict[str, Any]:
        """Get asset details"""
        return await self._request("GET", f"/v2/assets/{symbol}")
    
    # ───────────────────────────────────────────────────────────
    # Clock & Calendar
    # ───────────────────────────────────────────────────────────
    
    async def get_clock(self) -> Dict[str, Any]:
        """Get market clock (is_open, next_open, next_close)"""
        return await self._request("GET", "/v2/clock")
    
    async def is_market_open(self) -> bool:
        """Check if market is currently open"""
        clock = await self.get_clock()
        return clock.get("is_open", False)
    
    async def get_calendar(self, start: Optional[str] = None, end: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get market calendar"""
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self._request("GET", "/v2/calendar", params=params)
