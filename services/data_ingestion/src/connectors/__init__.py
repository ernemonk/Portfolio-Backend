"""Data source connectors."""

from .alpha_vantage import AlphaVantageConnector
from .binance import BinanceConnector
from .coingecko import CoinGeckoConnector
from .kraken import KrakenConnector
from .yahoo_finance import YahooFinanceConnector
from .coinpaprika import CoinpaprikaConnector
from .coincap import CoincapConnector
from .fmp import FinancialModelingPrepConnector
from .iex_cloud import IexCloudConnector

# Registry of all available connectors
CONNECTORS = {
    "alpha_vantage": AlphaVantageConnector,
    "binance_public": BinanceConnector,
    "coingecko": CoinGeckoConnector,
    "kraken_public": KrakenConnector,
    "yahoo_finance": YahooFinanceConnector,
    "coinpaprika": CoinpaprikaConnector,
    "coincap": CoincapConnector,
    "fmp": FinancialModelingPrepConnector,
    "iex_cloud": IexCloudConnector,
}

# Free connectors that don't require API keys
FREE_CONNECTORS = [
    "binance_public",
    "coingecko", 
    "kraken_public",
    "yahoo_finance",
    "coinpaprika",
    "coincap",
    "fmp",
    "iex_cloud",
]
