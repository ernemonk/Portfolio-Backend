"""
Backtesting Engine
━━━━━━━━━━━━━━━━━
Event-driven bar-by-bar backtester.

Walk through each candle, fire the strategy, simulate fills at the
NEXT candle's open (realistic — no look-ahead bias).

Assumptions:
  - Market orders fill at next-candle open
  - Limit orders fill if next candle's [low, high] covers the limit price
  - No partial fills
  - Fee charged both sides (default 0.1%)
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from trading_os.types.models import (
    OHLCV,
    OrderType,
    PortfolioSnapshot,
    StrategyContext,
    TradeSide,
)


class BacktestRequest(BaseModel):
    strategy_name: str
    pair: str
    ohlcv: list[OHLCV]
    initial_capital: float = 10_000.0
    params: dict = {}
    fee_pct: float = 0.1  # per-side fee %


class BacktestTrade(BaseModel):
    candle_index: int
    side: str
    quantity: float
    fill_price: float
    pnl_usd: Optional[float] = None
    status: str = "open"  # open | closed


class BacktestResult(BaseModel):
    strategy_name: str
    pair: str
    candles_tested: int
    initial_capital: float
    final_capital: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    profitable_trades: int
    loss_trades: int
    avg_trade_pnl_usd: float
    equity_curve: list[float]
    trades: list[BacktestTrade]


async def run_backtest(strategy, req: BacktestRequest) -> BacktestResult:
    candles = req.ohlcv
    if len(candles) < 5:
        return _empty(strategy.name, req)

    capital = req.initial_capital
    asset_qty = 0.0
    fee_rate = req.fee_pct / 100
    equity_curve: list[float] = []
    trades: list[BacktestTrade] = []
    last_trade_at: int = 0

    open_entry: Optional[BacktestTrade] = None

    for i in range(1, len(candles) - 1):
        current = candles[i]
        next_c  = candles[i + 1]
        past    = candles[:i]

        portfolio = PortfolioSnapshot(
            total_value_usd=capital + asset_qty * current.close,
            daily_pnl=0.0,
            daily_pnl_pct=0.0,
            weekly_pnl=0.0,
            positions=[],
            portfolio_heat_pct=0.0,
        )

        ctx = StrategyContext(
            pair=req.pair,
            current_price=current.close,
            ohlcv=past,
            portfolio_state=portfolio,
            params=req.params,
        )

        try:
            intent = await strategy.should_trade(ctx, last_trade_at)
        except Exception:
            intent = None

        if intent:
            # Determine fill price on next candle
            if intent.order_type == OrderType.MARKET:
                fill_price = next_c.open
                filled = True
            else:
                # Limit order: fill if price range covers limit level
                limit = intent.price or next_c.open
                filled = next_c.low <= limit <= next_c.high
                fill_price = limit if filled else 0.0

            if filled and fill_price > 0:
                qty = intent.quantity
                if intent.side == TradeSide.BUY:
                    cost = qty * fill_price * (1 + fee_rate)
                    if capital >= cost:
                        capital -= cost
                        asset_qty += qty
                        last_trade_at = next_c.timestamp
                        t = BacktestTrade(
                            candle_index=i,
                            side="buy",
                            quantity=qty,
                            fill_price=fill_price,
                        )
                        trades.append(t)
                        if open_entry is None:
                            open_entry = t

                elif intent.side == TradeSide.SELL:
                    sell_qty = min(qty, asset_qty)
                    if sell_qty > 0:
                        proceeds = sell_qty * fill_price * (1 - fee_rate)
                        capital += proceeds
                        asset_qty -= sell_qty
                        last_trade_at = next_c.timestamp

                        pnl: Optional[float] = None
                        if open_entry:
                            pnl = round(
                                (fill_price - open_entry.fill_price) * sell_qty
                                - sell_qty * fill_price * fee_rate * 2,
                                4,
                            )
                            open_entry.pnl_usd = pnl
                            open_entry.status = "closed"
                            open_entry = None

                        trades.append(BacktestTrade(
                            candle_index=i,
                            side="sell",
                            quantity=sell_qty,
                            fill_price=fill_price,
                            pnl_usd=pnl,
                            status="closed",
                        ))

        equity_curve.append(round(capital + asset_qty * current.close, 2))

    # Liquidate remainder at last close
    if asset_qty > 0:
        capital += asset_qty * candles[-1].close * (1 - fee_rate)
        asset_qty = 0.0

    final_capital = round(capital, 2)
    total_return = round((final_capital - req.initial_capital) / req.initial_capital * 100, 2)

    # Max drawdown
    peak = req.initial_capital
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100
        max_dd = max(max_dd, dd)

    # Annualised Sharpe (assumes daily candles)
    rets = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]
    if len(rets) > 1:
        avg = sum(rets) / len(rets)
        var = sum((r - avg) ** 2 for r in rets) / len(rets)
        std = var ** 0.5
        sharpe = round((avg / std * (252 ** 0.5)) if std > 0 else 0.0, 3)
    else:
        sharpe = 0.0

    closed = [t for t in trades if t.pnl_usd is not None]
    wins   = [t for t in closed if (t.pnl_usd or 0) > 0]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0.0
    avg_pnl  = round(sum(t.pnl_usd or 0 for t in closed) / max(len(closed), 1), 2)

    buy_trades = [t for t in trades if t.side == "buy"]

    return BacktestResult(
        strategy_name=strategy.name,
        pair=req.pair,
        candles_tested=len(candles),
        initial_capital=req.initial_capital,
        final_capital=final_capital,
        total_return_pct=total_return,
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=sharpe,
        win_rate=win_rate,
        total_trades=len(buy_trades),
        profitable_trades=len(wins),
        loss_trades=len(closed) - len(wins),
        avg_trade_pnl_usd=avg_pnl,
        equity_curve=equity_curve[-200:],   # keep response lean
        trades=closed[-20:],                 # last 20 closed trades
    )


def _empty(name: str, req: BacktestRequest) -> BacktestResult:
    return BacktestResult(
        strategy_name=name,
        pair=req.pair,
        candles_tested=len(req.ohlcv),
        initial_capital=req.initial_capital,
        final_capital=req.initial_capital,
        total_return_pct=0.0,
        max_drawdown_pct=0.0,
        sharpe_ratio=0.0,
        win_rate=0.0,
        total_trades=0,
        profitable_trades=0,
        loss_trades=0,
        avg_trade_pnl_usd=0.0,
        equity_curve=[],
        trades=[],
    )
