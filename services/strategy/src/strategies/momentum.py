"""
Momentum Strategy — RSI-based
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RSI < oversold_threshold  → BUY  (reversal expected)
RSI > overbought_threshold → SELL (exhaustion expected)

Uses Wilder's exponential smoothing for RS calculation.
Requires at least (rsi_period + 1) candles.

Params:
  rsi_period           — RSI window (default 14)
  oversold_threshold   — BUY  below this RSI (default 30)
  overbought_threshold — SELL above this RSI (default 70)
  trade_size_pct       — % of portfolio total per trade (default 5%)
  cooldown_hours       — min time between signals (default 4 h)
"""
from __future__ import annotations

import time
from typing import Optional

from trading_os.types.models import OrderType, StrategyContext, TradeIntent, TradeSide

from .base import BaseStrategy


def _rsi(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI. Returns 50 (neutral) when data is insufficient."""
    if len(closes) < period + 1:
        return 50.0

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


class MomentumStrategy(BaseStrategy):
    name = "momentum"
    description = "RSI momentum — buy oversold (<30), sell overbought (>70)"
    default_params: dict = {
        "rsi_period": 14,
        "oversold_threshold": 30,
        "overbought_threshold": 70,
        "trade_size_pct": 5.0,
        "cooldown_hours": 4,
    }

    async def should_trade(
        self,
        ctx: StrategyContext,
        last_trade_at: int = 0,
    ) -> Optional[TradeIntent]:
        params = {**self.default_params, **ctx.params}
        cooldown_ms = float(params["cooldown_hours"]) * 3_600_000
        now_ms = int(time.time() * 1000)

        if last_trade_at > 0 and (now_ms - last_trade_at) < cooldown_ms:
            return None

        period = int(params["rsi_period"])
        closes = [c.close for c in ctx.ohlcv] + [ctx.current_price]
        rsi = _rsi(closes, period)

        trade_value_usd = ctx.portfolio_state.total_value_usd * float(params["trade_size_pct"]) / 100
        quantity = round(trade_value_usd / ctx.current_price, 8)

        oversold  = float(params["oversold_threshold"])
        overbought = float(params["overbought_threshold"])

        if rsi < oversold:
            conf = round(min(0.95, (oversold - rsi) / oversold), 3)
            return TradeIntent(
                strategy_name=self.name,
                pair=ctx.pair,
                side=TradeSide.BUY,
                quantity=quantity,
                order_type=OrderType.MARKET,
                confidence=conf,
            )

        if rsi > overbought:
            conf = round(min(0.95, (rsi - overbought) / (100 - overbought)), 3)
            return TradeIntent(
                strategy_name=self.name,
                pair=ctx.pair,
                side=TradeSide.SELL,
                quantity=quantity,
                order_type=OrderType.MARKET,
                confidence=conf,
            )

        return None
