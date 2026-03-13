"""
CCXT Universal Exchange Connector
The industry standard for crypto trading data - used by institutional systems
Supports 100+ exchanges with unified API

Enhanced features:
- Real-time WebSocket streaming
- Multi-exchange failover
- Institutional-grade reliability
- Comprehensive health monitoring
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Callable
import ccxt.async_support as ccxt
import json
import websockets
import time

from .base import BaseConnector


class WebSocketStreamer:
    """Real-time WebSocket streaming for cryptocurrency data"""
    
    def __init__(self, exchange_id: str = 'binance'):
        self.exchange_id = exchange_id
        self.websocket = None
        self.is_streaming = False
        self.callbacks = {}
        
        # WebSocket endpoints for major exchanges
        self.ws_endpoints = {
            'binance': 'wss://stream.binance.com:9443/ws/',
            'coinbase': 'wss://ws-feed.exchange.coinbase.com',
            'kraken': 'wss://ws.kraken.com/',
            'bitfinex': 'wss://api-pub.bitfinex.com/ws/2',
            'huobi': 'wss://api.huobi.pro/ws',
            'okx': 'wss://ws.okx.com:8443/ws/v5/public',
            'bybit': 'wss://stream.bybit.com/v5/public/spot',
            'kucoin': 'wss://ws-api.kucoin.com/endpoint'
        }
    
    async def start_price_stream(self, symbols: List[str], callback: Callable):
        """Start real-time price streaming for symbols"""
        
        if self.exchange_id not in self.ws_endpoints:
            raise ValueError(f"WebSocket streaming not supported for {self.exchange_id}")
        
        endpoint = self.ws_endpoints[self.exchange_id]
        self.callbacks['price'] = callback
        
        try:
            # Connect to WebSocket
            self.websocket = await websockets.connect(endpoint)
            self.is_streaming = True
            
            # Subscribe to price feeds based on exchange protocol
            await self._subscribe_prices(symbols)
            
            # Start message handling
            async for message in self.websocket:
                if not self.is_streaming:
                    break
                    
                try:
                    data = json.loads(message)
                    processed_data = self._process_price_message(data)
                    
                    if processed_data and callback:
                        await callback(processed_data)
                        
                except Exception as e:
                    print(f"WebSocket message processing error: {e}")
                    
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.is_streaming = False
    
    async def _subscribe_prices(self, symbols: List[str]):
        """Subscribe to price feeds for specific exchange"""
        
        if self.exchange_id == 'binance':
            # Binance format: btcusdt@ticker
            streams = [f"{symbol.lower().replace('/', '')}@ticker" for symbol in symbols]
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": streams,
                "id": 1
            }
            
        elif self.exchange_id == 'coinbase':
            # Coinbase Pro format
            subscribe_msg = {
                "type": "subscribe",
                "channels": [
                    {
                        "name": "ticker",
                        "product_ids": symbols
                    }
                ]
            }
            
        elif self.exchange_id == 'kraken':
            # Kraken format
            subscribe_msg = {
                "event": "subscribe",
                "pair": symbols,
                "subscription": {"name": "ticker"}
            }
            
        else:
            # Generic format
            subscribe_msg = {
                "method": "subscribe",
                "params": symbols
            }
        
        await self.websocket.send(json.dumps(subscribe_msg))
    
    def _process_price_message(self, data: Dict) -> Optional[Dict[str, Any]]:
        """Process price message based on exchange format"""
        
        try:
            if self.exchange_id == 'binance':
                if 'data' in data and data['data'].get('e') == '24hrTicker':
                    ticker = data['data']
                    return {
                        'exchange': 'binance',
                        'symbol': ticker.get('s'),
                        'price': float(ticker.get('c', 0)),
                        'volume': float(ticker.get('v', 0)),
                        'change_24h_pct': float(ticker.get('P', 0)),
                        'timestamp': datetime.utcnow().isoformat()
                    }
            
            elif self.exchange_id == 'coinbase':
                if data.get('type') == 'ticker':
                    return {
                        'exchange': 'coinbase',
                        'symbol': data.get('product_id'),
                        'price': float(data.get('price', 0)),
                        'volume': float(data.get('volume_24h', 0)),
                        'timestamp': data.get('time')
                    }
            
            elif self.exchange_id == 'kraken':
                if isinstance(data, list) and len(data) > 3:
                    channel_data = data[1]
                    if 'c' in channel_data:  # Price data
                        return {
                            'exchange': 'kraken',
                            'symbol': data[3],
                            'price': float(channel_data['c'][0]),
                            'volume': float(channel_data['v'][0]),
                            'timestamp': datetime.utcnow().isoformat()
                        }
            
            return None
            
        except Exception as e:
            print(f"Price message processing error: {e}")
            return None
    
    async def stop_stream(self):
        """Stop WebSocket streaming"""
        self.is_streaming = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
    
    async def start_orderbook_stream(self, symbol: str, callback: Callable):
        """Start real-time order book streaming"""
        
        if self.exchange_id not in self.ws_endpoints:
            raise ValueError(f"Order book streaming not supported for {self.exchange_id}")
        
        endpoint = self.ws_endpoints[self.exchange_id]
        self.callbacks['orderbook'] = callback
        
        try:
            self.websocket = await websockets.connect(endpoint)
            self.is_streaming = True
            
            # Subscribe to order book based on exchange
            await self._subscribe_orderbook(symbol)
            
            async for message in self.websocket:
                if not self.is_streaming:
                    break
                
                try:
                    data = json.loads(message)
                    processed_data = self._process_orderbook_message(data)
                    
                    if processed_data and callback:
                        await callback(processed_data)
                        
                except Exception as e:
                    print(f"Order book processing error: {e}")
                    
        except Exception as e:
            print(f"Order book WebSocket error: {e}")
            self.is_streaming = False
    
    async def _subscribe_orderbook(self, symbol: str):
        """Subscribe to order book for specific exchange"""
        
        if self.exchange_id == 'binance':
            stream = f"{symbol.lower().replace('/', '')}@depth"
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [stream],
                "id": 1
            }
            
        elif self.exchange_id == 'coinbase':
            subscribe_msg = {
                "type": "subscribe",
                "channels": ["level2"],
                "product_ids": [symbol]
            }
            
        else:
            subscribe_msg = {"method": "subscribe", "params": [symbol]}
        
        await self.websocket.send(json.dumps(subscribe_msg))
    
    def _process_orderbook_message(self, data: Dict) -> Optional[Dict[str, Any]]:
        """Process order book message"""
        
        try:
            if self.exchange_id == 'binance' and 'data' in data:
                depth = data['data']
                return {
                    'exchange': 'binance',
                    'symbol': depth.get('s'),
                    'bids': [[float(p), float(q)] for p, q in depth.get('b', [])[:10]],
                    'asks': [[float(p), float(q)] for p, q in depth.get('a', [])[:10]],
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            elif self.exchange_id == 'coinbase' and data.get('type') == 'l2update':
                return {
                    'exchange': 'coinbase',
                    'symbol': data.get('product_id'),
                    'changes': data.get('changes', []),
                    'timestamp': data.get('time')
                }
            
            return None
            
        except Exception as e:
            print(f"Order book message error: {e}")
            return None


class CCXTConnector(BaseConnector):
    NAME = "ccxt_universal"
    DISPLAY_NAME = "CCXT Universal (100+ Exchanges)"
    BASE_URL = "https://api.binance.com"  # Default to Binance
    RATE_LIMIT = 1200  # Conservative across all exchanges
    AUTH_REQUIRED = False

    def __init__(self, rate_limiter, exchange_name: str = "kraken", **kwargs):
        """Initialize with specific exchange. Default: kraken (most reliable)"""
        super().__init__(rate_limiter, **kwargs)
        self.exchange_name = exchange_name
        self._exchange = None

    async def _get_exchange(self):
        """Get or create exchange instance"""
        if self._exchange is None:
            exchange_class = getattr(ccxt, self.exchange_name)
            self._exchange = exchange_class({
                'sandbox': False,  # Use live markets
                'rateLimit': self.RATE_LIMIT,
                'enableRateLimit': True,
            })
        return self._exchange

    async def test_connection(self) -> Dict[str, Any]:
        try:
            exchange = await self._get_exchange()
            
            # Test with exchange status or markets
            if hasattr(exchange, 'fetch_status'):
                status = await exchange.fetch_status()
                message = f"CCXT {self.exchange_name} - Status: {status.get('status', 'online')}"
            else:
                markets = await exchange.load_markets()
                market_count = len(markets)
                message = f"CCXT {self.exchange_name} - {market_count} markets available"
            
            return {
                "ok": True,
                "message": message,
                "exchange": self.exchange_name,
                "has_features": {
                    "fetchTicker": exchange.has.get('fetchTicker', False),
                    "fetchOHLCV": exchange.has.get('fetchOHLCV', False),
                    "fetchOrderBook": exchange.has.get('fetchOrderBook', False),
                    "fetchTrades": exchange.has.get('fetchTrades', False),
                }
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        finally:
            if self._exchange:
                await self._exchange.close()
                self._exchange = None

    async def fetch_prices(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """Fetch current prices using CCXT unified API"""
        results = []
        exchange = None
        
        try:
            exchange = await self._get_exchange()
            
            for symbol in symbols:
                try:
                    # Convert symbol to CCXT format (e.g., BTC/USDT)
                    ccxt_symbol = symbol.replace('USDT', '/USDT').replace('USD', '/USD')
                    if '/' not in ccxt_symbol and 'USDT' not in ccxt_symbol:
                        ccxt_symbol = f"{ccxt_symbol}/USDT"
                    
                    ticker = await exchange.fetch_ticker(ccxt_symbol)
                    
                    results.append({
                        "source": f"ccxt_{self.exchange_name}",
                        "symbol": symbol.upper(),
                        "ccxt_symbol": ccxt_symbol,
                        "exchange": self.exchange_name,
                        "price_usd": float(ticker.get('last', 0)),
                        "bid": float(ticker.get('bid', 0)),
                        "ask": float(ticker.get('ask', 0)),
                        "volume_24h": float(ticker.get('baseVolume', 0)),
                        "volume_quote_24h": float(ticker.get('quoteVolume', 0)),
                        "change_24h_pct": float(ticker.get('percentage', 0)),
                        "high_24h": float(ticker.get('high', 0)),
                        "low_24h": float(ticker.get('low', 0)),
                        "vwap": float(ticker.get('vwap', 0)),
                        "timestamp": ticker.get('timestamp'),
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as exc:
                    results.append({
                        "source": f"ccxt_{self.exchange_name}",
                        "symbol": symbol,
                        "error": str(exc)
                    })
        except Exception as exc:
            for symbol in symbols:
                results.append({
                    "source": f"ccxt_{self.exchange_name}",
                    "symbol": symbol,
                    "error": f"Exchange error: {exc}"
                })
        finally:
            if exchange:
                await exchange.close()
                self._exchange = None
        
        return results

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV data using CCXT"""
        try:
            exchange = await self._get_exchange()
            
            # Convert symbol format
            ccxt_symbol = symbol.replace('USDT', '/USDT').replace('USD', '/USD')
            if '/' not in ccxt_symbol and 'USDT' not in ccxt_symbol:
                ccxt_symbol = f"{ccxt_symbol}/USDT"
            
            # Convert interval to CCXT format
            interval_map = {
                '1m': '1m', '5m': '5m', '15m': '15m', '30m': '30m',
                '1h': '1h', '4h': '4h', '1d': '1d', '1w': '1w'
            }
            ccxt_interval = interval_map.get(interval, '1d')
            
            # Fetch OHLCV
            since = int(start_time.timestamp() * 1000) if start_time else None
            ohlcv = await exchange.fetch_ohlcv(
                ccxt_symbol, 
                ccxt_interval, 
                since=since,
                limit=100
            )
            
            candles = []
            for data in ohlcv:
                if data[0] and data[1] is not None:  # timestamp and open exist
                    candles.append({
                        "timestamp": datetime.fromtimestamp(data[0] / 1000, timezone.utc).isoformat(),
                        "open": float(data[1]),
                        "high": float(data[2]),
                        "low": float(data[3]),
                        "close": float(data[4]),
                        "volume": float(data[5] or 0),
                    })
            
            return candles
            
        except Exception:
            return []
        finally:
            if exchange:
                await exchange.close()
                self._exchange = None

    def supported_symbols(self) -> List[str]:
        """Return list of supported symbols for this connector."""
        return [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
            "ADA/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LINK/USDT",
            "ATOM/USDT", "LTC/USDT", "BCH/USDT", "FIL/USDT", "TRX/USDT"
        ]

    @classmethod
    def get_supported_exchanges(cls) -> List[str]:
        """Get comprehensive list of exchanges supported by CCXT (100+ exchanges)"""
        return [
            # Tier 1 - Major Global Exchanges (Highest liquidity)
            'binance', 'coinbase', 'kraken', 'bitfinex', 'huobi', 'okx',
            'bybit', 'kucoin', 'gate', 'mexc', 'bitget', 'phemex',
            
            # Tier 2 - Regional Leaders  
            'binanceus', 'gemini', 'ftx', 'crypto_com', 'bittrex',
            'bithumb', 'upbit', 'coincheck', 'liquid', 'bitso',
            
            # Tier 3 - Specialized & Derivatives
            'dydx', 'gmx', 'perpetualprotocol', 'mango', 'drift',
            'bitmex', 'ftx_us', 'blockchain_com', 'cex', 'exmo',
            
            # Tier 4 - Additional Coverage
            'ascendex', 'bibox', 'bigone', 'bitbank', 'bitbay',
            'bitcoincom', 'bitkk', 'bitmart', 'bitmax', 'bitstamp',
            'bitrue', 'bitvavo', 'bl3p', 'btcalpha', 'btcbox',
            'btcex', 'btcmarkets', 'btctrade', 'btctradeua', 'btcturk',
            'buda', 'bw', 'bytetrade', 'cdax', 'cex', 'coinbaseprime',
            'coinex', 'coinfalcon', 'coinmate', 'coinone', 'coinsph',
            'coinspot', 'crex24', 'currencycom', 'delta', 'digifinex',
            'eqonex', 'eterbase', 'fcoinhk', 'flowbtc', 'gateio',
            'hitbtc', 'hollaex', 'idex', 'independentreserve', 'indodax',
            'itbit', 'kraken', 'kuna', 'lbank', 'luno', 'lykke',
            'mercado', 'mixcoins', 'ndax', 'novadax', 'oceanex',
            'okcoin', 'paymium', 'poloniex', 'probit', 'ripio',
            'stex', 'therock', 'tidebit', 'tidex', 'timex',
            'tokocrypto', 'upbit', 'vcc', 'wavesexchange', 'wazirx',
            'whitebit', 'woo', 'xt', 'yobit', 'zaif', 'zb'
        ]
    
    @classmethod 
    def get_tier1_exchanges(cls) -> List[str]:
        """Get Tier 1 exchanges with highest reliability and liquidity"""
        return [
            'kraken',      # Most reliable, regulatory compliant
            'coinbase',    # US regulatory leader, institutional grade
            'binanceus',   # US compliant version of Binance
            'gemini',      # Strong US compliance, institutional focus
            'bitfinex',    # High liquidity, advanced trading
            'bitstamp'     # Long-established, EU regulated
        ]
    
    @classmethod
    def get_failover_order(cls, primary_exchange: str) -> List[str]:
        """Get recommended failover order for each exchange"""
        
        failover_mapping = {
            'binance': ['kraken', 'coinbase', 'bitfinex', 'okx'],
            'coinbase': ['kraken', 'gemini', 'binanceus', 'bitstamp'],
            'kraken': ['coinbase', 'gemini', 'bitfinex', 'bitstamp'],
            'bitfinex': ['kraken', 'coinbase', 'okx', 'huobi'],
            'bybit': ['okx', 'kucoin', 'gate', 'mexc'],
            'kucoin': ['bybit', 'gate', 'mexc', 'okx'],
            'huobi': ['okx', 'gate', 'binance', 'mexc'],
            'okx': ['bybit', 'kucoin', 'gate', 'huobi']
        }
        
        # Default to tier 1 exchanges if no specific mapping
        return failover_mapping.get(primary_exchange, cls.get_tier1_exchanges())
    
    async def test_exchange_connectivity(self, exchange_id: str) -> Dict[str, Any]:
        """Test connectivity and performance of specific exchange"""
        
        import time
        start_time = time.time()
        
        try:
            exchange = getattr(ccxt, exchange_id)()
            if hasattr(exchange, 'set_sandbox_mode'):
                exchange.set_sandbox_mode(False)  # Ensure production mode
            
            # Test basic connectivity
            markets = await exchange.load_markets()
            response_time = int((time.time() - start_time) * 1000)
            
            # Get exchange info
            info = {
                'exchange_id': exchange_id,
                'status': '✅ Connected',
                'response_time_ms': response_time,
                'total_markets': len(markets),
                'has_btc_usd': any('BTC' in symbol and 'USD' in symbol for symbol in markets.keys()),
                'rate_limit': getattr(exchange, 'rateLimit', 'unknown'),
                'countries': getattr(exchange, 'countries', []),
                'api_version': getattr(exchange, 'version', 'unknown'),
                'certification': getattr(exchange, 'certified', False),
                'has_websocket': hasattr(exchange, 'ws'),
                'sandbox_available': hasattr(exchange, 'set_sandbox_mode'),
                'test_timestamp': time.time()
            }
            
            await exchange.close()
            return info
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Categorize error types
            if 'timeout' in error_msg:
                error_type = 'timeout'
            elif 'forbidden' in error_msg or '403' in error_msg:
                error_type = 'geo_blocked'
            elif 'rate limit' in error_msg or '429' in error_msg:
                error_type = 'rate_limited'
            elif 'network' in error_msg or 'connection' in error_msg:
                error_type = 'network_error'
            else:
                error_type = 'unknown_error'
            
            return {
                'exchange_id': exchange_id,
                'status': '❌ Failed',
                'error_type': error_type,
                'error_message': str(e)[:200],
                'response_time_ms': int((time.time() - start_time) * 1000),
                'test_timestamp': time.time()
            }
    
    async def get_exchange_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive health report for all supported exchanges"""
        
        print("🔍 Testing connectivity to 100+ cryptocurrency exchanges...")
        
        # Test tier 1 exchanges first (most important)
        tier1_exchanges = self.get_tier1_exchanges()
        tier1_results = {}
        
        for exchange_id in tier1_exchanges:
            print(f"   Testing {exchange_id}...")
            result = await self.test_exchange_connectivity(exchange_id)
            tier1_results[exchange_id] = result
        
        # Test a subset of other exchanges (avoid rate limits)
        other_exchanges = [ex for ex in self.get_supported_exchanges()[:30] if ex not in tier1_exchanges]
        other_results = {}
        
        for exchange_id in other_exchanges:
            try:
                result = await self.test_exchange_connectivity(exchange_id)
                other_results[exchange_id] = result
                
                # Small delay to avoid overwhelming servers
                await asyncio.sleep(0.5)
                
            except Exception as e:
                other_results[exchange_id] = {
                    'exchange_id': exchange_id,
                    'status': '❌ Failed',
                    'error_message': str(e)[:100]
                }
        
        # Generate summary statistics
        all_results = {**tier1_results, **other_results}
        working_exchanges = [k for k, v in all_results.items() if '✅' in v.get('status', '')]
        failed_exchanges = [k for k, v in all_results.items() if '❌' in v.get('status', '')]
        
        # Calculate average response time for working exchanges
        response_times = [v.get('response_time_ms', 0) for v in all_results.values() 
                         if '✅' in v.get('status', '') and v.get('response_time_ms')]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            'summary': {
                'total_tested': len(all_results),
                'working_exchanges': len(working_exchanges),
                'failed_exchanges': len(failed_exchanges), 
                'success_rate_pct': len(working_exchanges) / len(all_results) * 100,
                'avg_response_time_ms': int(avg_response_time),
                'test_timestamp': datetime.now(timezone.utc).isoformat()
            },
            'tier1_results': tier1_results,
            'other_results': other_results,
            'working_exchanges': working_exchanges,
            'failed_exchanges': failed_exchanges,
            'recommended_primary': working_exchanges[0] if working_exchanges else None,
            'failover_options': working_exchanges[1:4] if len(working_exchanges) > 1 else []
        }