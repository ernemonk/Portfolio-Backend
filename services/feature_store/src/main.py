"""
Institutional Feature Store Service
Stores computed technical indicators, risk metrics, and derived features
Used by hedge funds for systematic strategies
"""

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import APICredential, DataSource, DataIngestionLog, MarketCandle, PriceSnapshot


# ── Feature Store Models ──────────────────────────────────────────────────

class FeatureType(str, Enum):
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"  
    MACRO = "macro"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"


@dataclass
class TechnicalFeature:
    symbol: str
    timestamp: datetime
    feature_type: FeatureType
    name: str
    value: float
    timeframe: str
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class FeatureRequest(BaseModel):
    symbols: List[str]
    features: List[str] 
    timeframe: str = "1d"
    lookback_days: int = 30


class FeatureResponse(BaseModel):
    symbol: str
    features: Dict[str, float]
    timestamp: str
    timeframe: str


# ── Core Feature Computation Engine ───────────────────────────────────────

class InstitutionalFeatureEngine:
    """Hedge fund-grade feature computation"""
    
    def __init__(self):
        self.indicators = {}
    
    async def compute_technical_features(self, symbol: str, prices: List[Dict], timeframe: str) -> Dict[str, float]:
        """Compute technical indicators like hedge funds use"""
        if len(prices) < 20:
            return {}
        
        # Extract OHLCV data
        closes = [float(p.get('close', p.get('price_usd', 0))) for p in prices]
        highs = [float(p.get('high', p.get('price_usd', 0))) for p in prices]
        lows = [float(p.get('low', p.get('price_usd', 0))) for p in prices]
        volumes = [float(p.get('volume', p.get('volume_24h', 0))) for p in prices]
        
        features = {}
        
        try:
            # Core momentum indicators
            features.update(self._compute_momentum_features(closes, highs, lows))
            
            # Volatility measures
            features.update(self._compute_volatility_features(closes))
            
            # Mean reversion indicators
            features.update(self._compute_mean_reversion_features(closes))
            
            # Volume-based features
            features.update(self._compute_volume_features(closes, volumes))
            
            # Regime detection
            features.update(self._compute_regime_features(closes))
            
        except Exception as e:
            print(f"Error computing features for {symbol}: {e}")
        
        return features
    
    def _compute_momentum_features(self, closes: List[float], highs: List[float], lows: List[float]) -> Dict[str, float]:
        """Momentum indicators used by systematic traders"""
        features = {}
        
        if len(closes) >= 14:
            # RSI
            features['rsi_14'] = self._rsi(closes, 14)
            
            # Price momentum
            features['momentum_5d'] = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
            features['momentum_20d'] = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0
            
            # Moving average crossovers
            if len(closes) >= 50:
                ma_20 = sum(closes[-20:]) / 20
                ma_50 = sum(closes[-50:]) / 50
                features['ma_20_50_ratio'] = ma_20 / ma_50 - 1
                features['price_to_ma20'] = closes[-1] / ma_20 - 1
                features['price_to_ma50'] = closes[-1] / ma_50 - 1
        
        return features
    
    def _compute_volatility_features(self, closes: List[float]) -> Dict[str, float]:
        """Volatility measures for risk management"""
        features = {}
        
        if len(closes) >= 20:
            # Returns
            returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
            
            # Realized volatility
            features['volatility_20d'] = (sum(r**2 for r in returns[-20:]) / 20) ** 0.5 * (252 ** 0.5) * 100
            features['volatility_5d'] = (sum(r**2 for r in returns[-5:]) / 5) ** 0.5 * (252 ** 0.5) * 100
            
            # Downside volatility
            downside_returns = [r for r in returns[-20:] if r < 0]
            if downside_returns:
                features['downside_volatility_20d'] = (sum(r**2 for r in downside_returns) / len(downside_returns)) ** 0.5 * (252 ** 0.5) * 100
            else:
                features['downside_volatility_20d'] = 0
            
            # Maximum drawdown
            peak = max(closes)
            drawdown = (closes[-1] - peak) / peak * 100
            features['max_drawdown'] = drawdown
        
        return features
    
    def _compute_mean_reversion_features(self, closes: List[float]) -> Dict[str, float]:
        """Mean reversion signals"""
        features = {}
        
        if len(closes) >= 20:
            # Bollinger Band position
            ma_20 = sum(closes[-20:]) / 20
            std_20 = (sum((c - ma_20)**2 for c in closes[-20:]) / 20) ** 0.5
            
            features['bollinger_position'] = (closes[-1] - ma_20) / (2 * std_20) if std_20 > 0 else 0
            features['distance_from_ma20'] = (closes[-1] / ma_20 - 1) * 100
            
            # Z-score
            features['zscore_20d'] = (closes[-1] - ma_20) / std_20 if std_20 > 0 else 0
        
        return features
    
    def _compute_volume_features(self, closes: List[float], volumes: List[float]) -> Dict[str, float]:
        """Volume-based institutional signals"""
        features = {}
        
        if len(volumes) >= 20 and all(v > 0 for v in volumes[-20:]):
            # Volume trend
            vol_ma_5 = sum(volumes[-5:]) / 5
            vol_ma_20 = sum(volumes[-20:]) / 20
            features['volume_trend'] = vol_ma_5 / vol_ma_20 - 1
            
            # Price-volume correlation
            returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
            vol_changes = [(volumes[i] / volumes[i-1] - 1) for i in range(1, len(volumes))]
            
            if len(returns) >= 20:
                # Simple correlation
                mean_ret = sum(returns[-20:]) / 20
                mean_vol = sum(vol_changes[-20:]) / 20
                
                covariance = sum((returns[i] - mean_ret) * (vol_changes[i] - mean_vol) for i in range(-20, 0)) / 20
                ret_std = (sum((r - mean_ret)**2 for r in returns[-20:]) / 20) ** 0.5
                vol_std = (sum((v - mean_vol)**2 for v in vol_changes[-20:]) / 20) ** 0.5
                
                if ret_std > 0 and vol_std > 0:
                    features['price_volume_correlation'] = covariance / (ret_std * vol_std)
        
        return features
    
    def _compute_regime_features(self, closes: List[float]) -> Dict[str, float]:
        """Market regime detection features"""
        features = {}
        
        if len(closes) >= 50:
            # Trend strength
            ma_10 = sum(closes[-10:]) / 10
            ma_30 = sum(closes[-30:]) / 30
            ma_50 = sum(closes[-50:]) / 50
            
            features['trend_strength'] = (ma_10 - ma_50) / ma_50 * 100
            features['short_long_ma_ratio'] = ma_10 / ma_50 - 1
            
            # Market efficiency (autocorrelation)
            returns = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
            if len(returns) >= 30:
                lag1_corr = self._autocorrelation(returns[-30:], lag=1)
                features['return_autocorr_lag1'] = lag1_corr
        
        return features
    
    def _rsi(self, closes: List[float], period: int = 14) -> float:
        """RSI calculation"""
        if len(closes) < period + 1:
            return 50.0
        
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(-change)
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _autocorrelation(self, data: List[float], lag: int) -> float:
        """Calculate autocorrelation at given lag"""
        if len(data) <= lag:
            return 0.0
        
        n = len(data) - lag
        mean_val = sum(data) / len(data)
        
        c0 = sum((x - mean_val)**2 for x in data) / len(data)
        c_lag = sum((data[i] - mean_val) * (data[i + lag] - mean_val) for i in range(n)) / n
        
        if c0 == 0:
            return 0.0
        
        return c_lag / c0


# ── FastAPI Feature Store Service ─────────────────────────────────────────

app = FastAPI(
    title="Institutional Feature Store",
    description="Hedge fund-grade feature computation and storage",
    version="1.0.0"
)

feature_engine = InstitutionalFeatureEngine()


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "feature_store", 
        "timestamp": time.time()
    }


@app.post("/features/compute")
async def compute_features(
    request: FeatureRequest,
    db: AsyncSession = Depends(get_session)
) -> List[FeatureResponse]:
    """Compute institutional-grade features for symbols"""
    
    results = []
    
    for symbol in request.symbols:
        try:
            # Get recent price data
            query = select(PriceSnapshot).where(
                PriceSnapshot.symbol == symbol.upper()
            ).order_by(desc(PriceSnapshot.timestamp)).limit(100)
            
            result = await db.execute(query)
            price_records = result.scalars().all()
            
            if not price_records:
                # Try to get from candle data
                candle_query = select(MarketCandle).where(
                    MarketCandle.symbol == symbol.upper()
                ).order_by(desc(MarketCandle.timestamp)).limit(100)
                
                candle_result = await db.execute(candle_query)
                candle_records = candle_result.scalars().all()
                
                if candle_records:
                    prices = [
                        {
                            'close': c.close,
                            'high': c.high,
                            'low': c.low,
                            'volume': c.volume,
                            'timestamp': c.timestamp
                        } for c in reversed(candle_records)
                    ]
                else:
                    continue
            else:
                prices = [
                    {
                        'price_usd': p.price_usd,
                        'volume_24h': p.volume_24h or 0,
                        'timestamp': p.timestamp
                    } for p in reversed(price_records)
                ]
            
            # Compute features
            features = await feature_engine.compute_technical_features(
                symbol, prices, request.timeframe
            )
            
            # Filter requested features
            if request.features and 'all' not in request.features:
                features = {k: v for k, v in features.items() if k in request.features}
            
            results.append(FeatureResponse(
                symbol=symbol.upper(),
                features=features,
                timestamp=datetime.now(timezone.utc).isoformat(),
                timeframe=request.timeframe
            ))
            
        except Exception as exc:
            # Return empty features for failed symbols
            results.append(FeatureResponse(
                symbol=symbol.upper(),
                features={"error": str(exc)},
                timestamp=datetime.now(timezone.utc).isoformat(),
                timeframe=request.timeframe
            ))
    
    return results


@app.get("/features/available")
async def get_available_features():
    """List all available feature types"""
    return {
        "technical_indicators": [
            "rsi_14", "momentum_5d", "momentum_20d", 
            "ma_20_50_ratio", "price_to_ma20", "price_to_ma50"
        ],
        "volatility_measures": [
            "volatility_20d", "volatility_5d", "downside_volatility_20d", "max_drawdown"
        ],
        "mean_reversion": [
            "bollinger_position", "distance_from_ma20", "zscore_20d"
        ],
        "volume_analysis": [
            "volume_trend", "price_volume_correlation"
        ],
        "regime_detection": [
            "trend_strength", "short_long_ma_ratio", "return_autocorr_lag1"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3010)