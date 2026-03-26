# Database Setup: Historical Market Data

## Table: `market_candles`

This is where all your historical OHLCV data lives. The `load_historical_data.py` script populates it.

### Schema
```sql
CREATE TABLE market_candles (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,           -- e.g., "BTC", "AAPL"
    timestamp TIMESTAMP NOT NULL,           -- Date of the candle
    open FLOAT NOT NULL,                    -- Opening price
    high FLOAT NOT NULL,                    -- Highest price
    low FLOAT NOT NULL,                     -- Lowest price
    close FLOAT NOT NULL,                   -- Closing price
    volume FLOAT NOT NULL,                  -- Trading volume
    UNIQUE(symbol, timestamp)               -- One candle per symbol per day
);

CREATE INDEX idx_market_candles_symbol ON market_candles(symbol);
CREATE INDEX idx_market_candles_timestamp ON market_candles(timestamp);
```

### Example Data After Loading BTC & AAPL

```
symbol │ timestamp           │ open   │ high   │ low    │ close  │ volume
────────┼─────────────────────┼────────┼────────┼────────┼────────┼────────────
BTC    │ 2025-12-25 00:00:00 │ 43500  │ 44100  │ 43200  │ 43850  │ 250000000
BTC    │ 2025-12-26 00:00:00 │ 43850  │ 44500  │ 43700  │ 44200  │ 275000000
AAPL   │ 2025-12-25 00:00:00 │ 245.50 │ 248.25 │ 244.75 │ 246.80 │ 52000000
AAPL   │ 2025-12-26 00:00:00 │ 246.80 │ 249.00 │ 246.00 │ 248.15 │ 48000000
```

## Loading Data

### Script Usage
```bash
python3 load_historical_data.py \
  --symbol BTC \
  --source coingecko \
  --days 90
```

**Options:**
- `--symbol`: BTC, AAPL, ETH, SPY, etc
- `--source`: `coingecko` (crypto) or `yahoo` (stocks)
- `--days`: How many days back to load (default: 90)

### Example Commands

```bash
# Load last 90 days of Bitcoin
python3 load_historical_data.py --symbol BTC --source coingecko --days 90

# Load last 60 days of Apple stock
python3 load_historical_data.py --symbol AAPL --source yahoo --days 60

# Load last 180 days of Ethereum
python3 load_historical_data.py --symbol ETH --source coingecko --days 180

# Load last 30 days of S&P 500
python3 load_historical_data.py --symbol SPY --source yahoo --days 30
```

## Querying Your Data

### Count candles by symbol
```sql
SELECT symbol, COUNT(*) as candle_count
FROM market_candles
GROUP BY symbol
ORDER BY symbol;
```

### Get last 10 candles for BTC
```sql
SELECT *
FROM market_candles
WHERE symbol = 'BTC'
ORDER BY timestamp DESC
LIMIT 10;
```

### Check date range
```sql
SELECT symbol, 
       MIN(timestamp) as earliest,
       MAX(timestamp) as latest,
       COUNT(*) as candles
FROM market_candles
GROUP BY symbol;
```

### Calculate daily returns from historical data
```sql
SELECT 
    symbol,
    timestamp,
    close,
    LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_close,
    (close - LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp)) / 
    LAG(close) OVER (PARTITION BY symbol ORDER BY timestamp) as daily_return
FROM market_candles
WHERE symbol = 'BTC'
ORDER BY timestamp DESC
LIMIT 20;
```

## Using Data in Strategy Testing

Once loaded, your strategy can query this data:

```python
from sqlalchemy import create_engine, select
from market_candles import MarketCandle

engine = create_engine("postgresql://postgres:postgres@localhost:5432/trading_db")

# Get last 30 days of BTC data
with engine.connect() as conn:
    stmt = select(MarketCandle).where(
        MarketCandle.symbol == "BTC"
    ).order_by(MarketCandle.timestamp.desc()).limit(30)
    
    candles = conn.execute(stmt).fetchall()
    
    for candle in candles:
        print(f"{candle.timestamp}: close={candle.close}, volume={candle.volume}")
```

## Tips

✅ **Load enough history**: 90 days minimum for meaningful strategy testing
✅ **Check for gaps**: Stock markets close on weekends, crypto trades 24/7
✅ **Verify volume**: If volume is 0, data may be incomplete
✅ **Monitor DB size**: 90 days × multiple symbols = manageable (<10MB)

## Cleanup

```sql
-- Delete data for a symbol
DELETE FROM market_candles WHERE symbol = 'BTC';

-- Delete everything and start fresh
TRUNCATE market_candles;
```
