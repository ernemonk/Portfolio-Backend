#!/bin/bash

echo "Adding new free data sources..."

# Add CoinCap
echo "Adding CoinCap..."
curl -s -X POST "http://localhost:3009/sources" \
  -H "Content-Type: application/json" \
  -d '{"name":"coincap","display_name":"CoinCap (Free)","provider_type":"crypto","base_url":"https://api.coincap.io","requires_auth":false,"rate_limit_requests":100,"rate_limit_period_seconds":60,"poll_interval_seconds":120,"enabled_pairs":["bitcoin","ethereum","solana"],"is_active":true}'

echo ""

# Add Financial Modeling Prep
echo "Adding FMP..."
curl -s -X POST "http://localhost:3009/sources" \
  -H "Content-Type: application/json" \
  -d '{"name":"fmp","display_name":"Financial Modeling Prep (Free)","provider_type":"stock","base_url":"https://financialmodelingprep.com","requires_auth":false,"rate_limit_requests":10,"rate_limit_period_seconds":60,"poll_interval_seconds":600,"enabled_pairs":["AAPL","MSFT"],"is_active":true}'

echo ""

# Add IEX Cloud
echo "Adding IEX Cloud..."
curl -s -X POST "http://localhost:3009/sources" \
  -H "Content-Type: application/json" \
  -d '{"name":"iex_cloud","display_name":"IEX Cloud (Sandbox)","provider_type":"stock","base_url":"https://sandbox-api.iexapis.com","requires_auth":false,"rate_limit_requests":20,"rate_limit_period_seconds":60,"poll_interval_seconds":300,"enabled_pairs":["AAPL","MSFT"],"is_active":true}'

echo ""
echo "Done! Testing all free APIs..."
curl -s "http://localhost:3009/test-all-free" | python3 -m json.tool