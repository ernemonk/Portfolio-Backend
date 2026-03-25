"""
Integrated Trading System
Unifies Alpaca execution with data from Yahoo Finance and CoinGecko via HTTP service calls
"""

import asyncio
import logging
import httpx
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from alpaca_client import AlpacaClient, OrderSide, OrderType
from credential_manager import CredentialManager

logger = logging.getLogger(__name__)


@dataclass
class TradeConfig:
    """Configuration for trade execution"""
    symbol: str
    quantity: Optional[float] = None
    notional: Optional[float] = None  # Dollar amount
    side: str = "buy"  # buy or sell
    order_type: str = "market"  # market, limit, stop
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "day"  # day, gtc, opq, cls
    extended_hours: bool = False
    asset_type: str = "stock"  # stock or crypto


class IntegratedTradingSystem:
    """
    Main trading system that coordinates:
    - Alpaca for execution (stocks & crypto)
    - Yahoo Finance for stock data (HTTP service)
    - CoinGecko for crypto data (HTTP service)
    """
    
    def __init__(self, data_ingestion_url: str = "http://data-ingestion:3009"):
        """
        Initialize trading system
        
        Args:
            data_ingestion_url: Base URL for data ingestion service
        """
        self.alpaca: Optional[AlpacaClient] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        self.data_ingestion_url = data_ingestion_url
        self.is_paper = True  # Default to paper trading
    
    async def initialize(self, paper: bool = True):
        """
        Initialize Alpaca client with encrypted credentials
        
        Args:
            paper: Use paper trading (True) or live trading (False)
        """
        self.is_paper = paper
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        try:
            creds = await CredentialManager.get_alpaca_credentials()
            self.alpaca = AlpacaClient(
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                paper=paper
            )
            logger.info(f"✓ Initialized Alpaca client ({'PAPER' if paper else 'LIVE'} mode)")
        except Exception as e:
            logger.error(f"✗ Failed to initialize Alpaca: {e}")
            raise
    
    async def close(self):
        """Clean up HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
    
    # ───────────────────────────────────────────────────────────
    # Trading Operations (Alpaca)
    # ───────────────────────────────────────────────────────────
    
    async def place_trade(self, config: TradeConfig) -> Dict[str, Any]:
        """
        Place a trade order via Alpaca
        
        Args:
            config: TradeConfig with order details
        
        Returns:
            Order confirmation with order_id and status
        """
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            order = await self.alpaca.place_order(
                symbol=config.symbol,
                quantity=config.quantity or (config.notional / (await self._get_price(config.symbol, config.asset_type))),
                side=OrderSide[config.side.upper()],
                order_type=OrderType[config.order_type.upper()],
                time_in_force=config.time_in_force,
                limit_price=config.limit_price if config.order_type == "limit" else None,
                stop_price=config.stop_price if config.order_type == "stop" else None,
                extended_hours=config.extended_hours
            )
            
            return {
                "status": "success",
                "order_id": order.get("id"),
                "symbol": order.get("symbol"),
                "quantity": order.get("qty"),
                "side": order.get("side"),
                "order_type": order.get("order_type"),
                "mode": "PAPER" if self.is_paper else "LIVE"
            }
        except Exception as e:
            logger.error(f"✗ Order placement failed: {e}")
            return {"status": "error", "error": str(e), "mode": "PAPER" if self.is_paper else "LIVE"}
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            positions = await self.alpaca.get_positions()
            return positions if positions else []
        except Exception as e:
            logger.error(f"✗ Failed to get positions: {e}")
            return []
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close a position by symbol"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            result = await self.alpaca.close_position(symbol)
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"✗ Failed to close position {symbol}: {e}")
            return {"status": "error", "error": str(e)}
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open order"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            await self.alpaca.cancel_order(order_id)
            return {"status": "success", "order_id": order_id}
        except Exception as e:
            logger.error(f"✗ Failed to cancel order {order_id}: {e}")
            return {"status": "error", "error": str(e)}
    
    # ───────────────────────────────────────────────────────────
    # Market Data (via HTTP service calls)
    # ───────────────────────────────────────────────────────────
    
    async def _get_price(self, symbol: str, asset_type: str = "stock") -> float:
        """Get current price for a symbol"""
        try:
            if asset_type.lower() == "crypto":
                data = await self.get_crypto_price(symbol)
            else:
                data = await self.get_stock_price(symbol)
            
            if data:
                return float(data.get("price", data.get("current_price", 0)))
            return 0.0
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol}: {e}")
            return 0.0
    
    async def get_stock_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current stock price from Yahoo Finance service
        
        Args:
            symbol: Stock ticker (e.g., "AAPL", "TSLA")
        
        Returns:
            Price data with quote info or None if error
        """
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized")
        
        try:
            response = await self.http_client.get(
                f"{self.data_ingestion_url}/finance/quote",
                params={"symbol": symbol}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"✗ Failed to get stock price for {symbol}: {e}")
            return None
    
    async def get_crypto_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get current crypto price from CoinGecko service
        
        Args:
            symbol: Crypto symbol (e.g., "BTC", "ETH")
        
        Returns:
            Price data with market info or None if error
        """
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized")
        
        try:
            response = await self.http_client.get(
                f"{self.data_ingestion_url}/coingecko/price",
                params={"symbol": symbol}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"✗ Failed to get crypto price for {symbol}: {e}")
            return None
    
    async def get_historical_data(
        self,
        symbol: str,
        asset_type: str = "stock",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get historical OHLCV data
        
        Args:
            symbol: Asset symbol
            asset_type: "stock" or "crypto"
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            List of OHLCV data points or None if error
        """
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized")
        
        try:
            params = {"symbol": symbol}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            
            endpoint = "/finance/historical" if asset_type == "stock" else "/coingecko/historical"
            response = await self.http_client.get(
                f"{self.data_ingestion_url}{endpoint}",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"✗ Failed to get historical data for {symbol}: {e}")
            return None
    
    # ───────────────────────────────────────────────────────────
    # Account & Portfolio
    # ───────────────────────────────────────────────────────────
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get current account information"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            account = await self.alpaca.get_account()
            
            return {
                "status": "success",
                "account": {
                    "buying_power": float(account.get("buying_power", 0)),
                    "cash": float(account.get("cash", 0)),
                    "portfolio_value": float(account.get("portfolio_value", 0)),
                    "equity": float(account.get("equity", 0)),
                    "status": account.get("status", "unknown"),
                    "account_number": account.get("account_number"),
                    "account_type": account.get("account_type"),
                },
                "mode": "PAPER" if self.is_paper else "LIVE"
            }
        except Exception as e:
            logger.error(f"✗ Failed to get account info: {e}")
            return {
                "status": "error",
                "error": str(e),
                "mode": "PAPER" if self.is_paper else "LIVE"
            }
    
    async def get_portfolio_value(self) -> Optional[float]:
        """Get total portfolio value"""
        try:
            account_info = await self.get_account_info()
            if account_info["status"] == "success":
                return account_info["account"]["portfolio_value"]
            return None
        except Exception as e:
            logger.warning(f"✗ Failed to get portfolio value: {e}")
            return None
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            account = await self.alpaca.get_account()
            positions = await self.alpaca.get_positions()
            
            total_position_value = 0.0
            total_gain_loss = 0.0
            
            if positions:
                for pos in positions:
                    total_position_value += float(pos.get("market_value", 0))
                    total_gain_loss += float(pos.get("unrealized_pl", 0))
            
            return {
                "status": "success",
                "account": {
                    "equity": float(account.get("equity", 0)),
                    "buying_power": float(account.get("buying_power", 0)),
                    "cash": float(account.get("cash", 0)),
                    "portfolio_value": float(account.get("portfolio_value", 0)),
                    "initial_equity": float(account.get("initial_equity", 0)),
                },
                "positions": {
                    "count": len(positions) if positions else 0,
                    "total_value": total_position_value,
                    "total_gain_loss": total_gain_loss,
                    "total_gain_loss_pct": (total_gain_loss / total_position_value * 100) if total_position_value > 0 else 0,
                    "list": positions if positions else []
                },
                "mode": "PAPER" if self.is_paper else "LIVE",
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"✗ Failed to get portfolio summary: {e}")
            return {
                "status": "error",
                "error": str(e),
                "mode": "PAPER" if self.is_paper else "LIVE"
            }
    
    # ───────────────────────────────────────────────────────────
    # System Health & Status
    # ───────────────────────────────────────────────────────────
    
    async def health_check(self) -> Dict[str, Any]:
        """Check system health and connectivity"""
        checks = {
            "alpaca_connected": False,
            "data_ingestion_available": False,
            "http_client_ready": self.http_client is not None,
            "mode": "PAPER" if self.is_paper else "LIVE"
        }
        
        # Check Alpaca connectivity
        try:
            if self.alpaca:
                market_status = await self.alpaca.is_market_open()
                checks["alpaca_connected"] = market_status is not None
                checks["market_open"] = market_status
        except Exception as e:
            logger.warning(f"Alpaca health check failed: {e}")
        
        # Check data ingestion service
        try:
            if self.http_client:
                response = await self.http_client.get(
                    f"{self.data_ingestion_url}/health",
                    timeout=5.0
                )
                checks["data_ingestion_available"] = response.status_code == 200
        except Exception as e:
            logger.warning(f"Data ingestion health check failed: {e}")
        
        return checks
    
    async def is_market_open(self) -> bool:
        """Check if market is currently open"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            return await self.alpaca.is_market_open()
        except Exception as e:
            logger.warning(f"Failed to check market status: {e}")
            return False
    
    async def get_market_calendar(self) -> Optional[List[Dict[str, Any]]]:
        """Get market calendar for next trading days"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            return await self.alpaca.get_calendar()
        except Exception as e:
            logger.warning(f"Failed to get market calendar: {e}")
            return None


# ───────────────────────────────────────────────────────────
# Example Usage
# ───────────────────────────────────────────────────────────

async def main():
    """Example: Initialize and use the trading system"""
    
    system = IntegratedTradingSystem()
    
    try:
        # Initialize in paper mode (safe testing)
        await system.initialize(paper=True)
        logger.info("System initialized successfully")
        
        # Check system health
        health = await system.health_check()
        logger.info(f"Health check: {health}")
        
        # Get account info
        account_info = await system.get_account_info()
        logger.info(f"Account: {account_info}")
        
        # Get stock price
        stock_price = await system.get_stock_price("AAPL")
        logger.info(f"AAPL: {stock_price}")
        
        # Get crypto price
        crypto_price = await system.get_crypto_price("BTC")
        logger.info(f"BTC: {crypto_price}")
        
        # Get positions
        positions = await system.get_positions()
        logger.info(f"Positions: {positions}")
        
        # Get portfolio summary
        summary = await system.get_portfolio_summary()
        logger.info(f"Portfolio: {summary}")
        
    finally:
        await system.close()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Run main
    asyncio.run(main())
