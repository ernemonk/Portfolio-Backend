"""
Institutional Real-Time Stream Processing Service
Handles WebSocket streams like hedge funds use for low-latency data
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum

import websockets
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.websockets import WebSocketState
from pydantic import BaseModel

# ── Stream Models ──────────────────────────────────────────────────────────

class StreamType(str, Enum):
    TICKER = "ticker"
    TRADE = "trade"
    ORDERBOOK = "orderbook"
    CANDLE = "candle"


@dataclass
class StreamMessage:
    stream_type: StreamType
    exchange: str
    symbol: str
    data: Dict[str, Any]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.stream_type,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }


class StreamSubscription(BaseModel):
    exchange: str
    symbols: List[str]
    stream_types: List[StreamType]


# ── Exchange WebSocket Handlers ────────────────────────────────────────────

class BinanceStreamHandler:
    """Binance WebSocket stream handler"""
    
    def __init__(self, callback: Callable[[StreamMessage], None]):
        self.callback = callback
        self.base_url = "wss://stream.binance.com:9443/ws"
        self.connections = {}
    
    async def subscribe_ticker(self, symbols: List[str]):
        """Subscribe to ticker streams"""
        streams = [f"{symbol.lower()}@ticker" for symbol in symbols]
        stream_url = f"{self.base_url}/{'/'.join(streams)}"
        
        await self._connect_and_listen(stream_url, "ticker")
    
    async def subscribe_trades(self, symbols: List[str]):
        """Subscribe to trade streams"""
        streams = [f"{symbol.lower()}@trade" for symbol in symbols]
        stream_url = f"{self.base_url}/{'/'.join(streams)}"
        
        await self._connect_and_listen(stream_url, "trade")
    
    async def _connect_and_listen(self, url: str, stream_type: str):
        """Connect to WebSocket and listen for messages"""
        try:
            async with websockets.connect(url) as websocket:
                self.connections[stream_type] = websocket
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        if stream_type == "ticker":
                            msg = StreamMessage(
                                stream_type=StreamType.TICKER,
                                exchange="binance",
                                symbol=data['s'],
                                data={
                                    "price": float(data['c']),
                                    "volume": float(data['v']),
                                    "change_pct": float(data['P']),
                                    "high": float(data['h']),
                                    "low": float(data['l'])
                                },
                                timestamp=datetime.fromtimestamp(data['E'] / 1000, timezone.utc)
                            )
                        elif stream_type == "trade":
                            msg = StreamMessage(
                                stream_type=StreamType.TRADE,
                                exchange="binance",
                                symbol=data['s'],
                                data={
                                    "price": float(data['p']),
                                    "quantity": float(data['q']),
                                    "side": "buy" if data['m'] else "sell",
                                    "trade_id": data['t']
                                },
                                timestamp=datetime.fromtimestamp(data['T'] / 1000, timezone.utc)
                            )
                        
                        await self.callback(msg)
                        
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        
        except Exception as e:
            print(f"WebSocket connection error: {e}")


class CoinbaseStreamHandler:
    """Coinbase Pro WebSocket handler"""
    
    def __init__(self, callback: Callable[[StreamMessage], None]):
        self.callback = callback
        self.base_url = "wss://ws-feed.exchange.coinbase.com"
    
    async def subscribe_ticker(self, symbols: List[str]):
        """Subscribe to ticker streams"""
        message = {
            "type": "subscribe",
            "product_ids": symbols,
            "channels": ["ticker"]
        }
        
        await self._connect_and_listen(message)
    
    async def _connect_and_listen(self, subscribe_msg: Dict):
        """Connect and listen to Coinbase streams"""
        try:
            async with websockets.connect(self.base_url) as websocket:
                # Send subscription message
                await websocket.send(json.dumps(subscribe_msg))
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        if data.get('type') == 'ticker':
                            msg = StreamMessage(
                                stream_type=StreamType.TICKER,
                                exchange="coinbase",
                                symbol=data['product_id'],
                                data={
                                    "price": float(data['price']),
                                    "volume": float(data['volume_24h']),
                                    "best_bid": float(data['best_bid']),
                                    "best_ask": float(data['best_ask'])
                                },
                                timestamp=datetime.fromisoformat(data['time'].replace('Z', '+00:00'))
                            )
                            await self.callback(msg)
                            
                    except Exception as e:
                        print(f"Error processing Coinbase message: {e}")
                        
        except Exception as e:
            print(f"Coinbase WebSocket error: {e}")


# ── Stream Aggregator ──────────────────────────────────────────────────────

class InstitutionalStreamAggregator:
    """Aggregates streams from multiple exchanges"""
    
    def __init__(self):
        self.redis_client = None
        self.active_subscriptions = {}
        self.websocket_clients = []
        
    async def init_redis(self, redis_url: str = "redis://localhost:6379"):
        """Initialize Redis connection for stream caching"""
        self.redis_client = redis.from_url(redis_url)
    
    async def subscribe_to_exchange(self, exchange: str, symbols: List[str], stream_types: List[StreamType]):
        """Subscribe to exchange streams"""
        
        if exchange == "binance":
            handler = BinanceStreamHandler(self._handle_stream_message)
            
            for stream_type in stream_types:
                if stream_type == StreamType.TICKER:
                    asyncio.create_task(handler.subscribe_ticker(symbols))
                elif stream_type == StreamType.TRADE:
                    asyncio.create_task(handler.subscribe_trades(symbols))
        
        elif exchange == "coinbase":
            handler = CoinbaseStreamHandler(self._handle_stream_message)
            
            for stream_type in stream_types:
                if stream_type == StreamType.TICKER:
                    asyncio.create_task(handler.subscribe_ticker(symbols))
    
    async def _handle_stream_message(self, message: StreamMessage):
        """Handle incoming stream message"""
        # Cache in Redis
        if self.redis_client:
            await self._cache_message(message)
        
        # Broadcast to WebSocket clients
        await self._broadcast_to_clients(message)
    
    async def _cache_message(self, message: StreamMessage):
        """Cache message in Redis with expiration"""
        try:
            key = f"stream:{message.exchange}:{message.symbol}:{message.stream_type}"
            value = json.dumps(message.to_dict())
            
            # Cache for 1 hour
            await self.redis_client.setex(key, 3600, value)
            
            # Also maintain a latest price cache
            if message.stream_type == StreamType.TICKER:
                latest_key = f"latest:{message.exchange}:{message.symbol}"
                await self.redis_client.setex(latest_key, 3600, json.dumps({
                    "price": message.data.get("price"),
                    "timestamp": message.timestamp.isoformat()
                }))
                
        except Exception as e:
            print(f"Redis cache error: {e}")
    
    async def _broadcast_to_clients(self, message: StreamMessage):
        """Broadcast to connected WebSocket clients"""
        if not self.websocket_clients:
            return
        
        message_json = json.dumps(message.to_dict())
        
        # Remove disconnected clients
        active_clients = []
        for client in self.websocket_clients:
            try:
                if client.client_state == WebSocketState.CONNECTED:
                    await client.send_text(message_json)
                    active_clients.append(client)
            except Exception:
                pass  # Client disconnected
        
        self.websocket_clients = active_clients
    
    def add_websocket_client(self, websocket: WebSocket):
        """Add WebSocket client for broadcasting"""
        self.websocket_clients.append(websocket)
    
    def remove_websocket_client(self, websocket: WebSocket):
        """Remove WebSocket client"""
        if websocket in self.websocket_clients:
            self.websocket_clients.remove(websocket)


# ── FastAPI Stream Service ─────────────────────────────────────────────────

app = FastAPI(
    title="Institutional Stream Service",
    description="Real-time market data streaming like hedge funds use",
    version="1.0.0"
)

stream_aggregator = InstitutionalStreamAggregator()


@app.on_event("startup")
async def startup():
    """Initialize streaming service"""
    print("Starting Institutional Stream Service on port 3011...")
    await stream_aggregator.init_redis()


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "stream_processor",
        "timestamp": time.time(),
        "active_clients": len(stream_aggregator.websocket_clients)
    }


@app.post("/subscribe")
async def subscribe_to_streams(subscription: StreamSubscription):
    """Subscribe to market data streams"""
    try:
        await stream_aggregator.subscribe_to_exchange(
            subscription.exchange,
            subscription.symbols,
            subscription.stream_types
        )
        
        return {
            "status": "subscribed",
            "exchange": subscription.exchange,
            "symbols": subscription.symbols,
            "stream_types": subscription.stream_types
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.websocket("/ws/stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data"""
    await websocket.accept()
    stream_aggregator.add_websocket_client(websocket)
    
    try:
        while True:
            # Keep connection alive and handle client messages
            try:
                data = await websocket.receive_text()
                # Client can send subscription requests via WebSocket
                message = json.loads(data)
                
                if message.get("type") == "subscribe":
                    await stream_aggregator.subscribe_to_exchange(
                        message.get("exchange"),
                        message.get("symbols", []),
                        [StreamType(t) for t in message.get("stream_types", [])]
                    )
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"WebSocket error: {e}")
                break
                
    finally:
        stream_aggregator.remove_websocket_client(websocket)


@app.get("/latest/{exchange}/{symbol}")
async def get_latest_price(exchange: str, symbol: str):
    """Get latest cached price"""
    try:
        if stream_aggregator.redis_client:
            key = f"latest:{exchange}:{symbol}"
            cached = await stream_aggregator.redis_client.get(key)
            
            if cached:
                return json.loads(cached)
        
        return {"error": "No cached data found"}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3011)