"""
Base strategy contract — every strategy implements this.
All strategies are stateless; state (last_trade_at) is owned by the service layer.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from trading_os.types.models import StrategyContext, TradeIntent


class BaseStrategy(ABC):
    name: str = "base"
    description: str = ""
    default_params: dict = {}

    @abstractmethod
    async def should_trade(
        self,
        ctx: StrategyContext,
        last_trade_at: int = 0,
    ) -> Optional[TradeIntent]:
        """
        Evaluate context and return a TradeIntent if a signal fires, else None.

        Args:
            ctx:           Read-only market + portfolio snapshot
            last_trade_at: Unix-ms of last trade by this strategy for this pair (0 = never)

        Contract: never raises — return None if signal cannot be computed.
        """
        ...

    def info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "default_params": self.default_params,
        }
