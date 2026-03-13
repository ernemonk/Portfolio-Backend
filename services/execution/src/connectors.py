"""
Exchange Connectors — Adapter Registry
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plugin-based adapter architecture. Core execution logic is 100% exchange-agnostic.

Every adapter implements ExchangeInterface:
    get_balance()   → dict[str, float]   # available balances by asset symbol
    place_order()   → OrderResult        # normalized fill result
    get_positions() → list[Position]     # open positions

Adding a new broker or venue — 3 steps, no core changes:
    1. Subclass ExchangeInterface (or CcxtAdapter for ccxt-backed exchanges)
    2. Set exchange_id = "my_venue"
    3. Register in EXCHANGE_REGISTRY: "my_venue": MyAdapter

EXCHANGE_REGISTRY:
    "paper"    → PaperAdapter     (simulation, default in dev / PAPER_MODE=true)
    "binance"  → BinanceAdapter   (spot, via ccxt)
    "kraken"   → KrakenAdapter    (spot, via ccxt)
    "coinbase" → CoinbaseAdapter  (spot, via ccxt)
    "alpaca"   → AlpacaAdapter    (equities + crypto, Alpaca REST API)

Credential resolution (per-venue env vars first, generic fallback):
    BINANCE_API_KEY / BINANCE_API_SECRET
    KRAKEN_API_KEY  / KRAKEN_API_SECRET
    COINBASE_API_KEY / COINBASE_API_SECRET
    ALPACA_API_KEY  / ALPACA_API_SECRET + ALPACA_BASE_URL
    fallback: EXCHANGE_API_KEY / EXCHANGE_API_SECRET
"""
from __future__ import annotations

import asyncio
import os
import uuid
from abc import ABC, abstractmethod

from trading_os.types.models import ApprovedTradeIntent, OrderResult, Position


# ─── Abstract Interface ───────────────────────────────────────────────────────

class ExchangeInterface(ABC):
    """
    Contract every exchange adapter must fulfill.

    Core trading logic imports ONLY this class — never a concrete adapter.
    The execution service routes to the correct implementation via
    EXCHANGE_REGISTRY[intent.venue].

    Design rules:
      - All methods are async
      - No exchange-specific types leak out (everything returns shared models)
      - Adapters handle their own retries and error normalization
      - Raise RuntimeError for unrecoverable setup errors (missing keys, etc.)
    """
    exchange_id: str = "abstract"

    @abstractmethod
    async def get_balance(self) -> dict[str, float]:
        """
        Return available (free) balances keyed by asset symbol.
        e.g. {"BTC": 0.5, "USDT": 1000.0, "ETH": 2.0}
        """
        ...

    @abstractmethod
    async def place_order(self, intent: ApprovedTradeIntent) -> OrderResult:
        """
        Submit an order and return a normalized OrderResult.
        Must never raise — return status='failed' on any exchange error.
        """
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """
        Return all open positions as a list of Position objects.
        Returns an empty list if the exchange has no open positions.
        """
        ...

    async def close(self) -> None:
        """Optional cleanup — close websocket sessions, HTTP clients, etc."""
        pass


# ─── Paper Adapter ────────────────────────────────────────────────────────────

class PaperAdapter(ExchangeInterface):
    """
    Simulated execution — no exchange connection, no API keys.
    Instant fills at intent.price with 0.1% fee.
    Used when PAPER_MODE=true or intent.venue='paper'.
    """
    exchange_id = "paper"

    async def get_balance(self) -> dict[str, float]:
        # Mirrors PAPER_POSITIONS in portfolio service
        return {"USDT": 10_000.0, "BTC": 0.1, "ETH": 1.5, "SOL": 10.0}

    async def place_order(self, intent: ApprovedTradeIntent) -> OrderResult:
        await asyncio.sleep(0.05)  # simulated network latency
        price    = intent.price or 0.0
        notional = intent.quantity * price
        return OrderResult(
            order_id        = str(uuid.uuid4()),
            status          = "filled",
            executed_price  = price,
            filled_quantity = intent.quantity,
            fee             = round(notional * 0.001, 8),  # 0.1% taker fee
            slippage_pct    = 0.0,
            fill_time_ms    = 50,
            is_paper        = True,
        )

    async def get_positions(self) -> list[Position]:
        # Paper positions are tracked by the portfolio service
        return []


# ─── ccxt Base Adapter ────────────────────────────────────────────────────────

class CcxtAdapter(ExchangeInterface):
    """
    Shared base for all ccxt-backed exchange adapters.

    To add a new ccxt-supported exchange (e.g. Bybit):
        class BybitAdapter(CcxtAdapter):
            exchange_id = "bybit"
        EXCHANGE_REGISTRY["bybit"] = BybitAdapter

    That's the entire change — nothing else in the codebase needs updating.
    """
    exchange_id: str = "abstract_ccxt"

    def __init__(self, api_key: str = "", api_secret: str = "", **ccxt_options):
        import ccxt.async_support as ccxt_async  # type: ignore
        klass = getattr(ccxt_async, self.exchange_id, None)
        if klass is None:
            raise ValueError(f"ccxt does not support exchange: '{self.exchange_id}'")
        self._exchange = klass({
            "apiKey":          api_key,
            "secret":          api_secret,
            "enableRateLimit": True,
            "options":         {"defaultType": "spot"},
            **ccxt_options,
        })

    async def get_balance(self) -> dict[str, float]:
        raw = await self._exchange.fetch_balance()
        return {
            asset: float(info["free"])
            for asset, info in raw.items()
            if isinstance(info, dict) and float(info.get("free") or 0) > 0
        }

    async def place_order(self, intent: ApprovedTradeIntent) -> OrderResult:
        import time as _time
        order_type = intent.order_type.value   # "market" | "limit" | "stop_limit"
        side       = intent.side.value         # "buy" | "sell"
        price      = intent.price
        t0         = _time.time()

        try:
            if order_type == "market":
                raw = await self._exchange.create_market_order(
                    intent.pair, side, intent.quantity
                )
            elif order_type == "limit" and price:
                raw = await self._exchange.create_limit_order(
                    intent.pair, side, intent.quantity, price
                )
            else:
                raw = await self._exchange.create_order(
                    intent.pair, order_type, side, intent.quantity, price
                )
        except Exception:
            return OrderResult(order_id=str(intent.id), status="failed", is_paper=False)

        fill_ms        = int((_time.time() - t0) * 1000)
        executed_price = raw.get("average") or raw.get("price") or price or 0.0
        filled_qty     = raw.get("filled", intent.quantity)
        fee            = (raw.get("fee") or {}).get("cost", 0.0)
        status         = {"closed": "filled", "open": "placed", "canceled": "failed"}.get(
            raw.get("status", "open"), "placed"
        )

        return OrderResult(
            order_id          = str(intent.id),
            exchange_order_id = raw.get("id"),
            status            = status,      # type: ignore[arg-type]
            executed_price    = float(executed_price),
            filled_quantity   = float(filled_qty),
            fee               = float(fee),
            slippage_pct      = (
                abs(float(executed_price) - float(price)) / float(price) * 100
                if price else 0.0
            ),
            fill_time_ms = fill_ms,
            is_paper     = False,
        )

    async def get_positions(self) -> list[Position]:
        try:
            balance = await self._exchange.fetch_balance()
            return [
                Position(
                    asset          = asset,
                    quantity       = float(info["total"]),
                    value_usd      = 0.0,   # prices not fetched here
                    allocation_pct = 0.0,
                )
                for asset, info in balance.items()
                if isinstance(info, dict) and float(info.get("total") or 0) > 0
            ]
        except Exception:
            return []

    async def close(self) -> None:
        await self._exchange.close()


# ─── Concrete ccxt Adapters ───────────────────────────────────────────────────

class BinanceAdapter(CcxtAdapter):
    """Binance spot — largest volume, most liquid pairs."""
    exchange_id = "binance"


class KrakenAdapter(CcxtAdapter):
    """Kraken — strong EU presence, high security reputation."""
    exchange_id = "kraken"


class CoinbaseAdapter(CcxtAdapter):
    """Coinbase Advanced Trade — primary US retail venue."""
    exchange_id = "coinbase"


# ─── Alpaca Adapter (Equities + Crypto) ───────────────────────────────────────

class AlpacaAdapter(ExchangeInterface):
    """
    Alpaca Markets — equities and crypto via Alpaca REST API.

    Extends asset_class support beyond crypto-spot.
    Enables equity strategies (MA crossover on AAPL, MSFT, etc.)
    alongside crypto strategies without changing core logic.

    Install: pip install alpaca-trade-api
    Env vars:
        ALPACA_API_KEY     (required)
        ALPACA_API_SECRET  (required)
        ALPACA_BASE_URL    (default: https://paper-api.alpaca.markets)
    """
    exchange_id = "alpaca"

    def __init__(
        self,
        api_key:    str = "",
        api_secret: str = "",
        base_url:   str = "https://paper-api.alpaca.markets",
    ):
        self._api_key    = api_key
        self._api_secret = api_secret
        self._base_url   = base_url
        self._client     = None

    def _client_instance(self):
        if self._client is None:
            try:
                import alpaca_trade_api as tradeapi  # type: ignore
            except ImportError:
                raise RuntimeError(
                    "alpaca-trade-api not installed. Run: pip install alpaca-trade-api"
                )
            self._client = tradeapi.REST(self._api_key, self._api_secret, self._base_url)
        return self._client

    async def get_balance(self) -> dict[str, float]:
        client  = self._client_instance()
        account = await asyncio.to_thread(client.get_account)
        return {
            "USD":    float(account.buying_power),
            "equity": float(account.equity),
        }

    async def place_order(self, intent: ApprovedTradeIntent) -> OrderResult:
        client = self._client_instance()
        # Alpaca uses ticker symbols, not slash-separated pairs (BTC/USD → BTC)
        symbol = intent.pair.split("/")[0] if "/" in intent.pair else intent.pair
        tif    = intent.time_in_force.value
        try:
            order = await asyncio.to_thread(
                lambda: client.submit_order(
                    symbol        = symbol,
                    qty           = intent.quantity,
                    side          = intent.side.value,
                    type          = intent.order_type.value,
                    time_in_force = tif,
                )
            )
            return OrderResult(
                order_id          = str(intent.id),
                exchange_order_id = order.id,
                status            = "placed",
                is_paper          = False,
            )
        except Exception:
            return OrderResult(order_id=str(intent.id), status="failed", is_paper=False)

    async def get_positions(self) -> list[Position]:
        client = self._client_instance()
        try:
            raw = await asyncio.to_thread(client.list_positions)
            return [
                Position(
                    asset          = p.symbol,
                    quantity       = float(p.qty),
                    value_usd      = float(p.market_value),
                    allocation_pct = 0.0,
                )
                for p in raw
            ]
        except Exception:
            return []


# ─── Registry ─────────────────────────────────────────────────────────────────
# To add a new exchange: create adapter above, add one line here.
# Zero changes required to execution/main.py, risk engine, or strategy engine.

EXCHANGE_REGISTRY: dict[str, type[ExchangeInterface]] = {
    "paper":    PaperAdapter,
    "binance":  BinanceAdapter,
    "kraken":   KrakenAdapter,
    "coinbase": CoinbaseAdapter,
    "alpaca":   AlpacaAdapter,
}


# ─── Connector Cache & Factory ────────────────────────────────────────────────

_connectors: dict[str, ExchangeInterface] = {}


def get_connector(venue: str | None = None) -> ExchangeInterface:
    """
    Return a cached adapter instance for the given venue.

    venue: any key in EXCHANGE_REGISTRY.
           None → env EXCHANGE_ID → "paper" (always safe default)

    Credential resolution order:
        1. {VENUE}_API_KEY / {VENUE}_API_SECRET  (e.g. BINANCE_API_KEY)
        2. EXCHANGE_API_KEY / EXCHANGE_API_SECRET  (generic fallback)
    """
    eid = (venue or os.getenv("EXCHANGE_ID", "paper")).lower()

    if eid not in EXCHANGE_REGISTRY:
        raise ValueError(
            f"Unknown venue '{eid}'. Registered venues: {list(EXCHANGE_REGISTRY)}"
        )

    if eid not in _connectors:
        klass = EXCHANGE_REGISTRY[eid]

        if eid == "paper":
            _connectors[eid] = klass()

        elif eid == "alpaca":
            _connectors[eid] = klass(
                api_key    = os.getenv("ALPACA_API_KEY", ""),
                api_secret = os.getenv("ALPACA_API_SECRET", ""),
                base_url   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
            )

        else:
            # Per-venue keys first, generic fallback
            key    = os.getenv(f"{eid.upper()}_API_KEY")    or os.getenv("EXCHANGE_API_KEY", "")
            secret = os.getenv(f"{eid.upper()}_API_SECRET") or os.getenv("EXCHANGE_API_SECRET", "")
            _connectors[eid] = klass(api_key=key, api_secret=secret)

    return _connectors[eid]


async def close_all() -> None:
    """Close all open connections. Called on execution service shutdown."""
    for connector in _connectors.values():
        await connector.close()
    _connectors.clear()

    """Async wrapper around a ccxt exchange."""

    def __init__(self, exchange_id: str, api_key: str = "", api_secret: str = ""):
        import ccxt.async_support as ccxt_async  # type: ignore
        klass = getattr(ccxt_async, exchange_id, None)
        if klass is None:
            raise ValueError(f"Unknown ccxt exchange: {exchange_id}")
        self._exchange = klass({
            "apiKey":    api_key,
            "secret":    api_secret,
            "enableRateLimit": True,
            "options":   {"defaultType": "spot"},
        })
        self.exchange_id = exchange_id

    async def close(self):
        await self._exchange.close()

    async def fetch_ticker(self, pair: str) -> dict:
        return await self._exchange.fetch_ticker(pair)

    async def place_order(self, intent: ApprovedTradeIntent) -> OrderResult:
        """
        Place a real order on the exchange.
        Returns an OrderResult with exchange-provided fill details.
        """
        order_type = intent.order_type.value      # "market" | "limit" | "stop_limit"
        side       = intent.side.value            # "buy" | "sell"
        pair       = intent.pair
        qty        = intent.quantity
        price      = intent.price                 # None for market orders

        import time as _time
        t0 = _time.time()

        try:
            if order_type == "market":
                raw = await self._exchange.create_market_order(pair, side, qty)
            elif order_type == "limit" and price:
                raw = await self._exchange.create_limit_order(pair, side, qty, price)
            else:
                raw = await self._exchange.create_order(pair, order_type, side, qty, price)
        except Exception as e:
            return OrderResult(
                order_id=str(intent.id),
                status="failed",
                is_paper=False,
            )

        fill_ms = int((_time.time() - t0) * 1000)
        executed_price = raw.get("average") or raw.get("price") or price or 0.0
        filled_qty     = raw.get("filled", qty)
        fee_info       = raw.get("fee") or {}
        fee            = fee_info.get("cost", 0.0)

        status_map = {
            "closed":   "filled",
            "open":     "placed",
            "canceled": "failed",
            "partial":  "partial",
        }
        raw_status = raw.get("status", "open")
        status     = status_map.get(raw_status, "placed")

        return OrderResult(
            order_id=str(intent.id),
            exchange_order_id=raw.get("id"),
            status=status,        # type: ignore[arg-type]
            executed_price=float(executed_price),
            filled_quantity=float(filled_qty),
            fee=float(fee),
            slippage_pct=abs(float(executed_price) - float(price or executed_price)) / float(price or executed_price or 1) * 100 if price else 0.0,
            fill_time_ms=fill_ms,
            is_paper=False,
        )


# ─── Factory ──────────────────────────────────────────────────────────────────

_connectors: dict[str, ExchangeConnector] = {}


def get_connector(exchange_id: Optional[str] = None) -> ExchangeConnector:
    """
    Return a cached connector for the given exchange.
    Keys from env: EXCHANGE_ID, EXCHANGE_API_KEY, EXCHANGE_API_SECRET.
    """
    eid     = exchange_id or os.getenv("EXCHANGE_ID", "binance")
    key     = os.getenv("EXCHANGE_API_KEY", "")
    secret  = os.getenv("EXCHANGE_API_SECRET", "")

    if eid not in _connectors:
        _connectors[eid] = ExchangeConnector(eid, key, secret)
    return _connectors[eid]


async def close_all():
    for c in _connectors.values():
        await c.close()
    _connectors.clear()
