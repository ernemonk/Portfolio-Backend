#!/bin/bash

# =============================================================================
# Restart Services with New Vault Configuration
# =============================================================================

set -e

echo "🔄 Restarting Trading OS Services with Vault Configuration..."
echo ""

# Navigate to Backend directory
cd "$(dirname "$0")"

# Step 1: Stop all services
echo "⏹️  Stopping all services..."
docker compose down
echo "✅ Services stopped"
echo ""

# Step 2: Verify .env.local exists
if [ ! -f ".env.local" ]; then
    echo "❌ ERROR: .env.local not found!"
    echo "   Please copy .env.example to .env.local and configure it."
    exit 1
fi
echo "✅ .env.local found"
echo ""

# Step 3: Check vault master key
if ! grep -q "VAULT_MASTER_KEY=" .env.local; then
    echo "⚠️  WARNING: VAULT_MASTER_KEY not found in .env.local"
    echo "   A default key will be used. Change it in production!"
fi
echo ""

# Step 4: Start services
echo "🚀 Starting all services..."
docker compose up -d
echo ""

# Step 5: Wait for services to be healthy
echo "⏳ Waiting for services to be healthy (30 seconds)..."
sleep 30
echo ""

# Step 6: Check service health
echo "🏥 Checking service health..."
echo ""

services=(
    "orchestrator:3001"
    "strategy:3002"
    "risk:3003"
    "execution:3004"
    "portfolio:3005"
    "analytics:3006"
    "config:3007"
    "local_ai:3008"
    "data_ingestion:3009"
)

healthy=0
unhealthy=0

for service_port in "${services[@]}"; do
    IFS=':' read -r name port <<< "$service_port"
    
    if curl -sf "http://localhost:$port/health" > /dev/null 2>&1; then
        echo "✅ $name (port $port) - HEALTHY"
        ((healthy++))
    else
        echo "❌ $name (port $port) - UNHEALTHY"
        ((unhealthy++))
    fi
done

echo ""
echo "📊 Health Summary: $healthy healthy, $unhealthy unhealthy"
echo ""

# Step 7: Check vault status
echo "🔐 Checking vault status..."
if curl -sf "http://localhost:3009/vault/status" > /dev/null 2>&1; then
    vault_status=$(curl -s "http://localhost:3009/vault/status")
    echo "✅ Vault is operational"
    echo "$vault_status" | jq '.' 2>/dev/null || echo "$vault_status"
else
    echo "❌ Vault API not responding"
    echo "   Check data_ingestion service: docker compose logs data_ingestion"
fi
echo ""

# Step 8: Display access URLs
echo "🌐 Access URLs:"
echo "   Frontend:      http://localhost:3000"
echo "   Trading Dashboard: http://localhost:3000/portal/trading"
echo "   Vault UI:      http://localhost:3000/portal/trading/data_ingestion"
echo "   Vault API:     http://localhost:3009/credentials"
echo ""

# Step 9: Display next steps
echo "📝 Next Steps:"
echo "   1. Open http://localhost:3000/portal/trading/data_ingestion"
echo "   2. Click '+ Add Credential' to store your first API key"
echo "   3. View CREDENTIAL_VAULT_GUIDE.md for usage examples"
echo ""

# Step 10: Show logs command
echo "📋 View logs:"
echo "   docker compose logs -f data_ingestion"
echo "   docker compose logs -f"
echo ""

if [ $unhealthy -eq 0 ]; then
    echo "🎉 All services are healthy and ready!"
else
    echo "⚠️  Some services are unhealthy. Check logs:"
    echo "   docker compose ps"
    echo "   docker compose logs <service_name>"
fi
