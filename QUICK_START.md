# 🚀 Quick Start: Paper Trading End-to-End

**Goal:** First paper trade with historical data - locally - no external deployment

---

## 🎯 The 4-Phase Plan

### Phase 1️⃣: Load Historical Data (15 min)
Pick 2-3 assets and load their history:

```bash
cd /Users/user/Projects/Portfolio/Backend

# Load BTC (last 90 days from CoinGecko)
python3 load_historical_data.py --symbol BTC --source coingecko --days 90

# Load AAPL (last 90 days from Yahoo Finance)
python3 load_historical_data.py --symbol AAPL --source yahoo --days 90

# Optional: Load more
python3 load_historical_data.py --symbol ETH --source coingecko --days 90
python3 load_historical_data.py --symbol SPY --source yahoo --days 90
```

**Verify data loaded:**
```bash
psql -U postgres -d trading_db -c "SELECT symbol, COUNT(*) as candles FROM market_candles GROUP BY symbol;"
```

---

### Phase 2️⃣: Deploy Services Locally (5 min)

```bash
cd /Users/user/Projects/Portfolio/Backend
docker-compose up -d
```

**Verify all services running:**
```bash
# Should show 12 containers running
docker-compose ps
```

**Test endpoints:**
```bash
curl http://localhost:3004/health     # Execution
curl http://localhost:3009/health     # Data Ingestion
curl http://localhost:3007/health     # Config
```

---

### Phase 3️⃣: Store Alpaca Credentials (5 min)

```bash
curl -X POST http://localhost:3007/credentials \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "alpaca",
    "api_key": "YOUR_ALPACA_API_KEY",
    "api_secret": "YOUR_ALPACA_SECRET"
  }'
```

Get your keys from: https://app.alpaca.markets/account (paper trading account)

---

### Phase 4️⃣: Place Paper Trade (5 min)

```bash
# Initialize trading system in PAPER mode
curl -X POST http://localhost:3004/execution/initialize \
  -H "Content-Type: application/json" \
  -d '{"paper": true}'

# Place order for 0.01 BTC
curl -X POST http://localhost:3004/execution/place-trade \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC",
    "quantity": 0.01,
    "side": "buy",
    "order_type": "market"
  }'

# Check positions
curl http://localhost:3004/execution/positions

# View trade in database
psql -U postgres -d trading_db -c "SELECT * FROM trades LIMIT 1;"
```

---

## ✅ Success Checklist

- [x] Historical data loaded: `SELECT COUNT(*) FROM market_candles;` > 0
- [ ] All services running: `docker-compose ps` shows 12/12
- [ ] Alpaca credentials stored in vault
- [ ] Paper order placed successfully
- [ ] Trade visible in `trades` table
- [ ] Can see positions: `GET /execution/positions`

---

## 🔧 What You Get

| Component | Status | What It Does |
|-----------|--------|-------------|
| **Historical Data** | ✅ Your choice | Real OHLCV data for backtesting & testing |
| **Strategy** | Momentum RSI | Generates signals from historical data |
| **Risk Manager** | Paper mode | Approves orders with safety limits |
| **Alpaca Paper** | 🚀 Ready | Execute orders in paper account ($100K) |
| **Portfolio Tracker** | Real prices | Uses historical data to track PnL |

---

## 🚨 Troubleshooting

**"No data for symbol"**
→ Make sure you ran Phase 1 first

**"Service not responding"**
→ Check `docker-compose logs` for errors

**"Alpaca credentials not found"**
→ Make sure you ran the POST request in Phase 3

**"Trade not placed"**
→ Check that execution service is running

---

## 📊 Available Assets to Load

**Crypto:**
```
BTC, ETH, SOL, ADA, DOGE, XRP, AVAX, POLY, LINK, UNI
```

**Stocks:**
```
AAPL, MSFT, TSLA, GOOGL, AMZN, NVDA, SPY, QQQ, IWM, GLD
```

Pick what you want to trade!

---

## 🎯 Next: Full Pipeline

Once Phase 1-4 work, run the full pipeline:

```bash
curl -X POST http://localhost:3001/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC",
    "data_source": "coingecko"
  }'
```

This triggers: Data → Strategy → Risk → Execution → Portfolio

**Done! 🎉**
