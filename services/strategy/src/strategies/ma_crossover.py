"""
MA-Crossover Strategy
━━━━━━━━━━━━━━━━━━━━
Golden cross (short SMA crosses ABOVE long SMA) → BUY
Death  cross (short SMA crosses BELOW long SMA) → SELL

Crossing is confirmed by comparing the relationship in consecutive bars.
Needs at least (long_period + 1) candles.

Params:
  short_period   — fast SMA window (default 20)
  long_period    — slow SMA window (default 50)
  trade_size_pct — % of portfolio per trade (default 5%)
  cooldown_hours — min hours between signals (default 6)
"""
from __future__ import annotations

import time
from typing import Optional

from trading_os.types.models import OrderType, StrategyContext, TradeIntent, TradeSide

from .base import BaseStrategy


def _sma(closes: list[float], period: int) -> float:
    if len(closes) < period:
        return closes[-1] if closes else 0.0
    return sum(closes[-period:]) / period


class MACrossoverStrategy(BaseStrategy):
    name = "ma_crossover"
    description = "MA-Crossover — golden cross BUY / death cross SELL (SMA20 vs SMA50)"
    default_params: dict = {
        "short_period": 20,
        "long_period": 50,
        "trade_size_pct": 5.0,
        "cooldown_hours": 6,
    }

    async def should_trade(
        self,
        ctx: StrategyContext,
        last_trade_at: int = 0,
    ) -> Optional[TradeIntent]:
        params = {**self.default_params, **ctx.params}
        short_p = int(params["short_period"])
        long_p  = int(params["long_period"])
        cooldown_ms = float(params["cooldown_hours"]) * 3_600_000
        now_ms = int(time.time() * 1000)

        if last_trade_at > 0 and (now_ms - last_trade_at) < cooldown_ms:
            return None

        closes = [c.close for c in ctx.ohlcv]
        if len(closes) < long_p + 1:
            return None  # not enough history

        # Current bar
        cur_short = _sma(closes, short_p)
        cur_long  = _sma(closes, long_p)

        # Previous bar (drop last close)
        prev = closes[:-1]
        prev_short = _sma(prev, short_p)
        prev_long  = _sma(prev, long_p)

        trade_value = ctx.portfolio_state.total_value_usd * float(params["trade_size_pct"]) / 100
        quantity = round(trade_value / ctx.current_price, 8)

        # Golden cross
        if prev_short <= prev_long and cur_short > cur_long:
            gap_pct = (cur_short - cur_long) / cur_long if cur_long else 0
            return TradeIntent(
                strategy_name=self.name,
                pair=ctx.pair,
                side=TradeSide.BUY,
                quantity=quantity,
                order_type=OrderType.MARKET,
                confidence=round(min(0.85, abs(gap_pct) * 100), 3),
            )

        # Death cross
        if prev_short >= prev_long and cur_short < cur_long:
            gap_pct = (cur_long - cur_short) / cur_long if cur_long else 0
            return TradeIntent(
                strategy_name=self.name,
                pair=ctx.pair,
                side=TradeSide.SELL,
                quantity=quantity,
                order_type=OrderType.MARKET,
                confidence=round(min(0.85, abs(gap_pct) * 100), 3),
            )

        return None
