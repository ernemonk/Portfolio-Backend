#!/usr/bin/env python3
"""
Load historical market data into PostgreSQL
Usage: python3 load_historical_data.py --symbol BTC --source coingecko --days 90
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent / "services" / "data_ingestion" / "src"))
sys.path.insert(0, str(Path(__file__).parent / "services" / "execution" / "src"))

from coingecko_client import CoinGeckoClient
from yahoo_finance_client import YahooFinanceClient

# PostgreSQL imports
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert

# Database connection
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/trading_db"
Base = declarative_base()

class MarketCandle(Base):
    """Market candle data"""
    __tablename__ = "market_candles"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), index=True)
    timestamp = Column(DateTime, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)


async def load_coingecko_data(symbol: str, days: int = 90):
    """Load crypto data from CoinGecko"""
    print(f"\n📊 Loading {symbol} from CoinGecko (last {days} days)...")
    
    client = CoinGeckoClient()
    
    try:
        # Fetch historical data
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        data = await client.get_historical_data(
            symbol=symbol,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat()
        )
        
        if not data:
            print(f"❌ No data returned for {symbol}")
            return 0
        
        # Transform to market_candles format
        candles = []
        for point in data:
            candles.append({
                "symbol": symbol,
                "timestamp": datetime.fromisoformat(point["date"]),
                "open": float(point.get("open", point["close"])),
                "high": float(point.get("high", point["close"])),
                "low": float(point.get("low", point["close"])),
                "close": float(point["close"]),
                "volume": float(point.get("volume", 0))
            })
        
        # Insert into database
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            for candle in candles:
                stmt = insert(MarketCandle).values(**candle).on_conflict_do_nothing()
                session.execute(stmt)
            
            session.commit()
            print(f"✅ Loaded {len(candles)} candles for {symbol}")
            return len(candles)
        
        finally:
            session.close()
    
    except Exception as e:
        print(f"❌ Error loading {symbol}: {str(e)}")
        return 0


async def load_yahoo_data(symbol: str, days: int = 90):
    """Load stock data from Yahoo Finance"""
    print(f"\n📈 Loading {symbol} from Yahoo Finance (last {days} days)...")
    
    client = YahooFinanceClient()
    
    try:
        # Fetch historical data
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        data = await client.get_historical_data(
            symbol=symbol,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat()
        )
        
        if not data:
            print(f"❌ No data returned for {symbol}")
            return 0
        
        # Transform to market_candles format
        candles = []
        for point in data:
            candles.append({
                "symbol": symbol,
                "timestamp": datetime.fromisoformat(point["date"]),
                "open": float(point.get("open", point["close"])),
                "high": float(point.get("high", point["close"])),
                "low": float(point.get("low", point["close"])),
                "close": float(point["close"]),
                "volume": float(point.get("volume", 0))
            })
        
        # Insert into database
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            for candle in candles:
                stmt = insert(MarketCandle).values(**candle).on_conflict_do_nothing()
                session.execute(stmt)
            
            session.commit()
            print(f"✅ Loaded {len(candles)} candles for {symbol}")
            return len(candles)
        
        finally:
            session.close()
    
    except Exception as e:
        print(f"❌ Error loading {symbol}: {str(e)}")
        return 0


async def verify_data(symbol: str):
    """Verify data was loaded"""
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        count = session.query(MarketCandle).filter(MarketCandle.symbol == symbol).count()
        session.close()
        
        if count > 0:
            print(f"✅ Verified: {count} candles for {symbol} in database")
        else:
            print(f"❌ No candles found for {symbol}")
        
        return count
    
    except Exception as e:
        print(f"❌ Error verifying: {str(e)}")
        return 0


async def main():
    parser = argparse.ArgumentParser(description="Load historical market data")
    parser.add_argument("--symbol", required=True, help="Symbol to load (BTC, AAPL, etc)")
    parser.add_argument("--source", required=True, choices=["coingecko", "yahoo"], help="Data source")
    parser.add_argument("--days", type=int, default=90, help="Days of history to load")
    
    args = parser.parse_args()
    
    print(f"\n🚀 Loading historical data for {args.symbol}...")
    print(f"   Source: {args.source}")
    print(f"   Days: {args.days}")
    
    if args.source == "coingecko":
        rows = await load_coingecko_data(args.symbol, args.days)
    else:
        rows = await load_yahoo_data(args.symbol, args.days)
    
    if rows > 0:
        await verify_data(args.symbol)
        print(f"\n✅ SUCCESS: {args.symbol} data loaded and verified")
    else:
        print(f"\n❌ FAILED: No data loaded for {args.symbol}")


if __name__ == "__main__":
    asyncio.run(main())
