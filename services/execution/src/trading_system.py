"""
Integrated Trading System
Unifies Alpaca execution, Yahoo Finance, and CoinGecko data sources
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from alpaca_client import AlpacaClient, OrderSide, OrderType
from coingecko_client import CoinGeckoClient
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

class IntegratedTradingSystem:
    """
    Main trading system that coordinates:
    - Alpaca for execution (stocks)
    - Yahoo Finance for stock data
    - CoinGecko for crypto data
    """
    
    def __init__(self):
        """Initialize all clients"""
        self.alpaca: Optional[AlpacaClient] = None
        self.coingecko = CoinGeckoClient()
        self.is_paper = True  # Default to paper trading
    
    async def initialize(self, paper: bool = True):
        """
        Initialize Alpaca client with encrypted credentials
        
        Args:
            paper: Use paper trading (True) or live trading (False)
        """
        self.is_paper = paper
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
    
    # ───────────────────────────────────────────────────────────
    # Trading Operations (Alpaca)
    # ───────────────────────────────────────────────────────────
    
    async def place_trade(self, config: TradeConfig) -> Dict[str, Any]:
        """
        Place a trade order
        
        Args:
            config: TradeConfig with order details
        
        Returns:
            Order confirmation with order_id
        """
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        
        try:
            order = await self.alpaca.place_order(
                symbol=config.symbol,
                qty=config.quantity,
                notional=config.notional,
                side=OrderSide(config.side),
                order_type=OrderType(config.order_type),
                limit_price=config.limit_price,
                stop_price=config.stop_price,
                time_in_force=config.time_in_force,
                extended_hours=config.extended_hours
            )
            logger.info(f"✓ Order placed: {config.symbol} {config.side} {config.quantity or config.notional}")
            return order
        except Exception as e:
            logger.error(f"✗ Failed to place trade: {e}")
            raise
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        return await self.alpaca.get_positions()
    
    async def close_position(self, symbol: str, qty: Optional[float] = None) -> Dict[str, Any]:
        """Close a position"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        return await self.alpaca.close_position(symbol, qty)
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account details"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        return await self.alpaca.get_account()
    
    async def get_buying_power(self) -> float:
        """Get available buying power"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        return await self.alpaca.get_buying_power()
    
    async def is_market_open(self) -> bool:
        """Check if market is open"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        return await self.alpaca.is_market_open()
    
    # ───────────────────────────────────────────────────────────
    # Market Data (Yahoo Finance + CoinGecko)
    # ───────────────────────────────────────────────────────────
    
    async def get_stock_price(self, symbol: str) -> Optional[float]:
        """Get current stock price"""
        try:
            # Use Alpaca for stock quotes
            if self.alpaca:
                from yahoo_finance_client import YahooFinanceClient
                yf = YahooFinanceClient()
                quote = await yf.get_quote(symbol)
                return quote.get("regularMarketPrice")
        except Exception as e:
            logger.warning(f"Failed to get stock price for {symbol}: {e}")
            return None
    
    async def get_crypto_price(self, crypto_id: str, currency: str = "usd") -> Optional[float]:
        """Get current crypto price"""
        try:
            prices = await self.coingecko.get_price(crypto_id, vs_currency=currency)
            return prices.get(crypto_id, {}).get(currency)
        except Exception as e:
            logger.warning(f"Failed to get crypto price for {crypto_id}: {e}")
            return None
    
    async def get_market_data(
        self, 
        symbol: str,
        is_crypto: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get comprehensive market data"""
        try:
            if is_crypto:
                return await self.coingecko.get_market_data(symbol)
            else:
                from yahoo_finance_client import YahooFinanceClient
                yf = YahooFinanceClient()
                return await yf.get_stock_details(symbol)
        except Exception as e:
            logger.warning(f"Failed to get market data for {symbol}: {e}")
            return None
    
    async def get_historical_data(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "1mo",
        is_crypto: bool = False
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV data"""
        try:
            if is_crypto:
                return await self.coingecko.get_historical_data(symbol, interval, period)
            else:
                from yahoo_finance_client import YahooFinanceClient
                yf = YahooFinanceClient()
                return await yf.get_historical_data(symbol, interval, period)
        except Exception as e:
            logger.warning(f"Failed to get historical data for {symbol}: {e}")
            return []
    
    # ───────────────────────────────────────────────────────────
    # Portfolio Analysis
    # ───────────────────────────────────────────────────────────
    
    async def get_portfolio_value(self) -> float:
        """Get total portfolio equity"""
        if not self.alpaca:
            raise RuntimeError("Alpaca client not initialized")
        return await self.alpaca.get_account_equity()
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary"""
        try:
            account = await self.get_account_info()
            positions = await self.get_positions()
            
            return {
                "equity": float(account.get("equity", 0)),
                "cash": float(account.get("cash", 0)),
                "buying_power": float(account.get("buying_power", 0)),
                "portfolio_value": float(account.get("portfolio_value", 0)),
                "day_change": float(account.get("last_equity", 0)) - float(account.get("equity", 0)),
                "open_positions": len(positions),
                "positions": positions,
            }
        except Exception as e:
            logger.error(f"Failed to get portfolio summary: {e}")
            raise
    
    # ───────────────────────────────────────────────────────────
    # Health & Status
    # ───────────────────────────────────────────────────────────
    
    async def health_check(self) -> Dict[str, Any]:
        """Check system health"""
        status = {
            "alpaca": "disconnected",
            "market_open": False,
            "mode": "PAPER" if self.is_paper else "LIVE"
        }
        
        try:
            if self.alpaca:
                status["market_open"] = await self.alpaca.is_market_open()
                status["alpaca"] = "connected"
        except Exception as e:
            logger.warning(f"Alpaca health check failed: {e}")
        
        return status

# ─────────────────────────────────────────────────────────────────────────────
# Singleton instance
# ─────────────────────────────────────────────────────────────────────────────

_trading_system: Optional[IntegratedTradingSystem] = None

async def get_trading_system() -> IntegratedTradingSystem:
    """Get or create trading system singleton"""
    global _trading_system
    if _trading_system is None:
        _trading_system = IntegratedTradingSystem()
        # Paper mode by default
        await _trading_system.initialize(paper=True)
    return _trading_system
