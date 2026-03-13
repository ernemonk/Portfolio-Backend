"""
DCA (Dollar-Cost Averaging) Strategy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Buy a fixed USD amount at regular time intervals, regardless of price.
Optionally gated by min/max price guards.

Params:
  interval_hours  — how often to buy (default 24 h)
  amount_usd      — USD to spend per buy (default 50)
  max_price       — skip buy if price above this (None = no cap)
  min_price       — skip buy if price below this (None = no floor)
"""
from __future__ import annotations

import time
from typing import Optional

from trading_os.types.models import OrderType, StrategyContext, TradeIntent, TradeSide

from .base import BaseStrategy


class DCAStrategy(BaseStrategy):
    name = "dca"
    description = "Dollar-Cost Averaging — buy fixed USD amount at regular intervals"
    default_params: dict = {
        "interval_hours": 24,
        "amount_usd": 50.0,
        "max_price": None,
        "min_price": None,
    }

    async def should_trade(
        self,
        ctx: StrategyContext,
        last_trade_at: int = 0,
    ) -> Optional[TradeIntent]:
        params = {**self.default_params, **ctx.params}
        interval_ms = float(params["interval_hours"]) * 3_600_000
        now_ms = int(time.time() * 1000)

        # Not yet time for next interval
        if last_trade_at > 0 and (now_ms - last_trade_at) < interval_ms:
            return None

        price = ctx.current_price
        if price <= 0:
            return None

        max_p = params.get("max_price")
        min_p = params.get("min_price")
        if max_p is not None and price > float(max_p):
            return None
        if min_p is not None and price < float(min_p):
            return None

        amount_usd = float(params["amount_usd"])
        quantity = round(amount_usd / price, 8)

        return TradeIntent(
            strategy_name=self.name,
            pair=ctx.pair,
            side=TradeSide.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
            confidence=0.75,
        )
