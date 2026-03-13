"""
Institutional Backtesting Engine
Based on hedge fund backtesting systems for systematic strategies
"""

import asyncio
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable, Union
from dataclasses import dataclass, field
from enum import Enum

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

# ── Backtesting Models ─────────────────────────────────────────────────────

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Order:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    order_id: str = field(default_factory=lambda: str(int(time.time() * 1000000)))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class Trade:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    timestamp: datetime
    
    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.avg_price
    
    @property
    def is_long(self) -> bool:
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-8


@dataclass
class Portfolio:
    cash: float = 100000.0
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)
    
    @property
    def equity(self) -> float:
        return self.cash + sum(pos.market_value + pos.unrealized_pnl for pos in self.positions.values())
    
    @property
    def total_pnl(self) -> float:
        return sum(pos.realized_pnl + pos.unrealized_pnl for pos in self.positions.values())


# ── Strategy Framework ─────────────────────────────────────────────────────

class BaseStrategy:
    """Base class for institutional trading strategies"""
    
    def __init__(self, name: str, initial_capital: float = 100000.0):
        self.name = name
        self.portfolio = Portfolio(cash=initial_capital)
        self.orders = []
        self.current_time = None
        self.current_prices = {}
    
    def on_data(self, data: Dict[str, Any]) -> List[Order]:
        """Called on each data point. Override this method."""
        raise NotImplementedError("Strategy must implement on_data method")
    
    def on_trade(self, trade: Trade) -> None:
        """Called when an order is filled. Override for custom logic."""
        pass
    
    def buy(self, symbol: str, quantity: float, price: Optional[float] = None) -> Order:
        """Create buy order"""
        return Order(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET if price is None else OrderType.LIMIT,
            quantity=quantity,
            price=price,
            timestamp=self.current_time or datetime.now(timezone.utc)
        )
    
    def sell(self, symbol: str, quantity: float, price: Optional[float] = None) -> Order:
        """Create sell order"""
        return Order(
            symbol=symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET if price is None else OrderType.LIMIT,
            quantity=quantity,
            price=price,
            timestamp=self.current_time or datetime.now(timezone.utc)
        )
    
    def get_position(self, symbol: str) -> Position:
        """Get current position for symbol"""
        if symbol not in self.portfolio.positions:
            self.portfolio.positions[symbol] = Position(symbol=symbol)
        return self.portfolio.positions[symbol]
    
    def update_unrealized_pnl(self, symbol: str, current_price: float):
        """Update unrealized P&L for position"""
        position = self.get_position(symbol)
        if not position.is_flat:
            position.unrealized_pnl = (current_price - position.avg_price) * position.quantity


# ── Example Institutional Strategies ───────────────────────────────────────

class MomentumStrategy(BaseStrategy):
    """Simple momentum strategy like hedge funds use"""
    
    def __init__(self, name: str = "Momentum", lookback: int = 20, threshold: float = 0.02):
        super().__init__(name)
        self.lookback = lookback
        self.threshold = threshold
        self.price_history = {}
    
    def on_data(self, data: Dict[str, Any]) -> List[Order]:
        orders = []
        symbol = data.get('symbol')
        price = data.get('price', data.get('close'))
        
        if not symbol or not price:
            return orders
        
        # Update price history
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > self.lookback:
            self.price_history[symbol].pop(0)
        
        # Check momentum signal
        if len(self.price_history[symbol]) >= self.lookback:
            prices = self.price_history[symbol]
            momentum = (prices[-1] / prices[0] - 1)
            
            position = self.get_position(symbol)
            position_size = abs(position.quantity)
            max_position = self.portfolio.cash * 0.1 / price  # 10% of portfolio
            
            # Long signal
            if momentum > self.threshold and position.quantity <= 0:
                quantity = min(max_position, self.portfolio.cash * 0.05 / price)
                if quantity > 0:
                    orders.append(self.buy(symbol, quantity))
            
            # Short signal  
            elif momentum < -self.threshold and position.quantity >= 0:
                quantity = min(max_position, self.portfolio.cash * 0.05 / price)
                if quantity > 0:
                    orders.append(self.sell(symbol, quantity))
        
        return orders


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands"""
    
    def __init__(self, name: str = "MeanReversion", lookback: int = 20, std_dev: float = 2.0):
        super().__init__(name)
        self.lookback = lookback
        self.std_dev = std_dev
        self.price_history = {}
    
    def on_data(self, data: Dict[str, Any]) -> List[Order]:
        orders = []
        symbol = data.get('symbol')
        price = data.get('price', data.get('close'))
        
        if not symbol or not price:
            return orders
        
        # Update price history
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > self.lookback:
            self.price_history[symbol].pop(0)
        
        # Calculate Bollinger Bands
        if len(self.price_history[symbol]) >= self.lookback:
            prices = self.price_history[symbol]
            mean_price = sum(prices) / len(prices)
            std_price = (sum((p - mean_price)**2 for p in prices) / len(prices))**0.5
            
            upper_band = mean_price + (self.std_dev * std_price)
            lower_band = mean_price - (self.std_dev * std_price)
            
            position = self.get_position(symbol)
            max_position = self.portfolio.cash * 0.1 / price
            
            # Mean reversion signals
            if price < lower_band and position.quantity <= 0:  # Oversold, buy
                quantity = min(max_position, self.portfolio.cash * 0.05 / price)
                if quantity > 0:
                    orders.append(self.buy(symbol, quantity))
                    
            elif price > upper_band and position.quantity >= 0:  # Overbought, sell
                quantity = min(max_position, self.portfolio.cash * 0.05 / price)
                if quantity > 0:
                    orders.append(self.sell(symbol, quantity))
        
        return orders


# ── Backtesting Engine ─────────────────────────────────────────────────────

class InstitutionalBacktester:
    """Hedge fund-grade backtesting engine"""
    
    def __init__(self, commission_rate: float = 0.001, slippage_bp: float = 1.0):
        self.commission_rate = commission_rate
        self.slippage_bp = slippage_bp / 10000  # Convert basis points
        self.strategies = []
        
    def add_strategy(self, strategy: BaseStrategy):
        """Add strategy to backtest"""
        self.strategies.append(strategy)
    
    async def run_backtest(self, data: List[Dict[str, Any]], start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Run institutional backtest"""
        
        results = {}
        
        for strategy in self.strategies:
            print(f"Running backtest for {strategy.name}...")
            
            # Reset strategy
            strategy.portfolio = Portfolio(cash=strategy.portfolio.cash)
            strategy.orders = []
            
            for row in data:
                # Set current time and prices
                strategy.current_time = datetime.fromisoformat(row.get('timestamp', row.get('date')))
                symbol = row.get('symbol')
                price = float(row.get('price', row.get('close', 0)))
                
                if symbol and price > 0:
                    strategy.current_prices[symbol] = price
                    
                    # Update unrealized P&L
                    strategy.update_unrealized_pnl(symbol, price)
                    
                    # Generate orders
                    orders = strategy.on_data(row)
                    
                    # Execute orders
                    for order in orders:
                        trade = self._execute_order(strategy, order, price)
                        if trade:
                            self._update_position(strategy, trade)
                            strategy.on_trade(trade)
            
            # Calculate performance metrics
            performance = self._calculate_performance(strategy)
            results[strategy.name] = performance
        
        return results
    
    def _execute_order(self, strategy: BaseStrategy, order: Order, current_price: float) -> Optional[Trade]:
        """Execute order with slippage and commission"""
        
        # Apply slippage
        if order.side == OrderSide.BUY:
            execution_price = current_price * (1 + self.slippage_bp)
        else:
            execution_price = current_price * (1 - self.slippage_bp)
        
        # Check if we have enough cash/position
        if order.side == OrderSide.BUY:
            required_cash = order.quantity * execution_price * (1 + self.commission_rate)
            if strategy.portfolio.cash < required_cash:
                return None  # Insufficient funds
        else:
            position = strategy.get_position(order.symbol)
            if position.quantity < order.quantity:
                return None  # Insufficient position
        
        # Calculate commission
        commission = order.quantity * execution_price * self.commission_rate
        
        # Create trade
        trade = Trade(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=execution_price,
            commission=commission,
            timestamp=order.timestamp
        )
        
        # Update cash
        if order.side == OrderSide.BUY:
            strategy.portfolio.cash -= (trade.notional + commission)
        else:
            strategy.portfolio.cash += (trade.notional - commission)
        
        strategy.portfolio.trades.append(trade)
        return trade
    
    def _update_position(self, strategy: BaseStrategy, trade: Trade):
        """Update position after trade"""
        position = strategy.get_position(trade.symbol)
        
        if trade.side == OrderSide.BUY:
            # Calculate new average price
            if position.quantity >= 0:
                total_cost = (position.quantity * position.avg_price) + (trade.quantity * trade.price)
                total_quantity = position.quantity + trade.quantity
                position.avg_price = total_cost / total_quantity if total_quantity > 0 else 0
                position.quantity = total_quantity
            else:
                # Covering short position
                if trade.quantity <= abs(position.quantity):
                    # Partial cover
                    position.realized_pnl += (position.avg_price - trade.price) * trade.quantity
                    position.quantity += trade.quantity
                else:
                    # Full cover + new long
                    cover_quantity = abs(position.quantity)
                    position.realized_pnl += (position.avg_price - trade.price) * cover_quantity
                    
                    remaining_quantity = trade.quantity - cover_quantity
                    position.quantity = remaining_quantity
                    position.avg_price = trade.price
        
        else:  # SELL
            if position.quantity > 0:
                # Selling long position
                if trade.quantity <= position.quantity:
                    # Partial or full sale
                    position.realized_pnl += (trade.price - position.avg_price) * trade.quantity
                    position.quantity -= trade.quantity
                    if position.quantity == 0:
                        position.avg_price = 0
                else:
                    # Full sale + new short
                    sale_quantity = position.quantity
                    position.realized_pnl += (trade.price - position.avg_price) * sale_quantity
                    
                    remaining_quantity = trade.quantity - sale_quantity
                    position.quantity = -remaining_quantity
                    position.avg_price = trade.price
            else:
                # Adding to short position
                total_cost = abs(position.quantity * position.avg_price) + (trade.quantity * trade.price)
                total_quantity = abs(position.quantity) + trade.quantity
                position.avg_price = total_cost / total_quantity if total_quantity > 0 else 0
                position.quantity = -total_quantity
    
    def _calculate_performance(self, strategy: BaseStrategy) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics"""
        
        trades = strategy.portfolio.trades
        if not trades:
            return {"error": "No trades executed"}
        
        # Basic metrics
        total_pnl = strategy.portfolio.total_pnl
        final_equity = strategy.portfolio.equity
        initial_capital = 100000.0  # Assuming default
        total_return = (final_equity - initial_capital) / initial_capital
        
        # Trade statistics
        num_trades = len(trades)
        winning_trades = [t for t in trades if (t.price - strategy.get_position(t.symbol).avg_price) * (1 if t.side == OrderSide.SELL else -1) > 0]
        win_rate = len(winning_trades) / num_trades if num_trades > 0 else 0
        
        # Risk metrics
        daily_returns = self._calculate_daily_returns(trades)
        if len(daily_returns) > 1:
            volatility = np.std(daily_returns) * np.sqrt(252)  # Annualized
            sharpe_ratio = (total_return / volatility) if volatility > 0 else 0
            max_drawdown = self._calculate_max_drawdown(trades)
        else:
            volatility = 0
            sharpe_ratio = 0
            max_drawdown = 0
        
        return {
            "strategy_name": strategy.name,
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "total_return": total_return,
            "total_pnl": total_pnl,
            "num_trades": num_trades,
            "win_rate": win_rate,
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "trades": [t.__dict__ for t in trades[-10:]]  # Last 10 trades
        }
    
    def _calculate_daily_returns(self, trades: List[Trade]) -> List[float]:
        """Calculate daily returns from trades"""
        if not trades:
            return []
        
        # Group trades by day and calculate daily P&L
        daily_pnl = {}
        for trade in trades:
            date_key = trade.timestamp.date()
            if date_key not in daily_pnl:
                daily_pnl[date_key] = 0
            # Simplified P&L calculation
            daily_pnl[date_key] += trade.notional * (1 if trade.side == OrderSide.SELL else -1)
        
        returns = list(daily_pnl.values())
        return [(r / 100000) for r in returns]  # Normalize by initial capital
    
    def _calculate_max_drawdown(self, trades: List[Trade]) -> float:
        """Calculate maximum drawdown"""
        if not trades:
            return 0
        
        equity_curve = [100000.0]  # Starting equity
        running_pnl = 0
        
        for trade in trades:
            # Simplified equity calculation
            trade_pnl = trade.notional * (1 if trade.side == OrderSide.SELL else -1) - trade.commission
            running_pnl += trade_pnl
            equity_curve.append(100000.0 + running_pnl)
        
        peak = equity_curve[0]
        max_dd = 0
        
        for equity in equity_curve[1:]:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            max_dd = max(max_dd, drawdown)
        
        return max_dd


# ── API Models ─────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy_name: str
    symbols: List[str]
    start_date: str
    end_date: str
    parameters: Dict[str, Any] = {}
    initial_capital: float = 100000.0


class BacktestResponse(BaseModel):
    strategy_name: str
    performance_metrics: Dict[str, Any]
    status: str
    execution_time: float


# ── FastAPI Backtesting Service ────────────────────────────────────────────

app = FastAPI(
    title="Institutional Backtesting Engine",
    description="Hedge fund-grade backtesting for systematic strategies",
    version="1.0.0"
)

backtester = InstitutionalBacktester()


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "backtesting_engine",
        "timestamp": time.time()
    }


@app.get("/strategies")
async def list_strategies():
    """List available strategies"""
    return {
        "available_strategies": [
            {
                "name": "MomentumStrategy",
                "description": "Trend-following momentum strategy",
                "parameters": {"lookback": 20, "threshold": 0.02}
            },
            {
                "name": "MeanReversionStrategy", 
                "description": "Bollinger Band mean reversion strategy",
                "parameters": {"lookback": 20, "std_dev": 2.0}
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3012)