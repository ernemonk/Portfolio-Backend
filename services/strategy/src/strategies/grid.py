"""
Grid Trading Strategy
━━━━━━━━━━━━━━━━━━━━
Divide the recent price range into N evenly-spaced levels.
  • Price crosses DOWN through a level → BUY limit at that level
  • Price crosses UP   through a level → SELL limit at that level

Stateless — grid levels are recomputed from recent candles each evaluation.

Params:
  grid_count          — number of price levels (default 10)
  range_lookback      — candles used to establish the high/low range (default 20)
  amount_per_grid_usd — USD per triggered grid level (default 20)
"""
from __future__ import annotations

from typing import Optional

from trading_os.types.models import OrderType, StrategyContext, TradeIntent, TradeSide

from .base import BaseStrategy


class GridStrategy(BaseStrategy):
    name = "grid"
    description = "Grid trading — buy dips / sell rips within recent price range"
    default_params: dict = {
        "grid_count": 10,
        "range_lookback": 20,
        "amount_per_grid_usd": 20.0,
    }

    @staticmethod
    def _levels(low: float, high: float, count: int) -> list[float]:
        if high <= low or count < 2:
            return []
        step = (high - low) / (count - 1)
        return [round(low + i * step, 8) for i in range(count)]

    async def should_trade(
        self,
        ctx: StrategyContext,
        last_trade_at: int = 0,
    ) -> Optional[TradeIntent]:
        params = {**self.default_params, **ctx.params}
        lookback = int(params["range_lookback"])
        count = int(params["grid_count"])
        amount_usd = float(params["amount_per_grid_usd"])

        candles = ctx.ohlcv[-lookback:] if len(ctx.ohlcv) >= lookback else ctx.ohlcv
        if len(candles) < 2:
            return None

        low  = min(c.low  for c in candles)
        high = max(c.high for c in candles)
        prev_price = candles[-2].close
        curr_price = ctx.current_price
        quantity = round(amount_usd / curr_price, 8)

        for level in self._levels(low, high, count):
            # Crossed DOWN → buy
            if prev_price > level >= curr_price:
                return TradeIntent(
                    strategy_name=self.name,
                    pair=ctx.pair,
                    side=TradeSide.BUY,
                    quantity=quantity,
                    price=level,
                    order_type=OrderType.LIMIT,
                    confidence=0.65,
                )
            # Crossed UP → sell
            if prev_price < level <= curr_price:
                return TradeIntent(
                    strategy_name=self.name,
                    pair=ctx.pair,
                    side=TradeSide.SELL,
                    quantity=quantity,
                    price=level,
                    order_type=OrderType.LIMIT,
                    confidence=0.65,
                )
        return None
