#!/bin/bash

echo "=== FINAL FREE API TESTING REPORT ==="
echo "Testing all currently integrated free data APIs..."
echo ""

# Test all APIs
echo "1. Testing ALL free APIs:"
curl -s "http://localhost:3009/test-all-free" | python3 -m json.tool
echo ""

echo "2. Testing live data fetch from working APIs:"
echo ""

echo "▶ Coinpaprika (Crypto) - BTC & ETH prices:"
curl -s "http://localhost:3009/fetch/prices" \
  -X POST -H "Content-Type: application/json" \
  -d '{"source": "coinpaprika", "symbols": ["btc-bitcoin", "eth-ethereum"]}' | python3 -m json.tool
echo ""

echo "▶ CoinGecko (Crypto) - Top coins:"
curl -s "http://localhost:3009/fetch/prices" \
  -X POST -H "Content-Type: application/json" \
  -d '{"source": "coingecko", "symbols": ["BTC", "ETH"]}' | python3 -m json.tool
echo ""

echo "▶ Kraken (Crypto) - Major pairs:"
curl -s "http://localhost:3009/fetch/prices" \
  -X POST -H "Content-Type: application/json" \
  -d '{"source": "kraken_public", "symbols": ["BTCUSDT", "ETHUSDT"]}' | python3 -m json.tool
echo ""

echo "3. Current data source count:"
curl -s "http://localhost:3009/sources" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'Total sources: {len(data)}')
free_sources = [s for s in data if not s['requires_auth']]
print(f'Free sources: {len(free_sources)}')
for s in free_sources:
    print(f'  - {s[\"display_name\"]} ({s[\"name\"]})')
"

echo ""
echo "=== INTEGRATION COMPLETE! ==="