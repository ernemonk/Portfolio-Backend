# Trading OS Backend Services

Complete backend microservices for the Trading OS platform with PostgreSQL, Redis, and AI integration.

## ⚡ Quick Start

### Terminal 1: Backend
```bash
cd Portfolio-Backend
docker-compose up -d
```

### Terminal 2: Frontend
```bash
cd Portfolio
npm install
npm run dev
```

### Browser
Open http://localhost:3000

## 🚀 Quick Start

### Start All Backend Services (with Docker Compose)

```bash
# From Backend directory
./start-services.sh

# Or use docker-compose directly
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

This starts all 9 services in parallel:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **Portfolio Service** (port 3005)
- **Strategy Service** (port 3002)
- **Risk Service** (port 3003)
- **Execution Service** (port 3004)
- **Orchestrator Service** (port 3001)
- **Analytics Service** (port 3006)
- **Config Service** (port 3007)
- **Local AI Service** (port 3008)
- **Data Ingestion** (port 3009)

### Start Specific Service

```bash
# Start a single service
docker-compose up -d portfolio

# Rebuild and start
docker-compose up -d --build strategy
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (careful - removes data)
docker-compose down -v

# Stop specific service
docker-compose stop risk
```

### Monitor Services

```bash
# Check service status
docker-compose ps

# View service logs
docker-compose logs portfolio        # Single service
docker-compose logs -f               # All services (follow)
docker-compose logs --tail=50 risk   # Last 50 lines

# Check specific service health
curl http://localhost:3005/health    # Portfolio
curl http://localhost:3002/health    # Strategy
curl http://localhost:3003/health    # Risk
curl http://localhost:3004/health    # Execution
curl http://localhost:3001/health    # Orchestrator
curl http://localhost:3006/health    # Analytics
curl http://localhost:3007/health    # Config
curl http://localhost:3008/health    # Local AI
curl http://localhost:3009/health    # Data Ingestion
```

## 🔗 Service URLs

| Service | Port | Health Check |
|---------|------|--------------|
| Orchestrator | 3001 | http://localhost:3001/health |
| Strategy | 3002 | http://localhost:3002/health |
| Risk | 3003 | http://localhost:3003/health |
| Execution | 3004 | http://localhost:3004/health |
| Portfolio | 3005 | http://localhost:3005/health |
| Analytics | 3006 | http://localhost:3006/health |
| Config | 3007 | http://localhost:3007/health |
| Local AI | 3008 | http://localhost:3008/health |
| Data Ingestion | 3009 | http://localhost:3009/health |
| PostgreSQL | 5432 | `psql -h localhost -U trading_os trading_os` |
| Redis | 6379 | `redis-cli ping` |

## 🗄️ Database

### PostgreSQL

```bash
# Connect to database
psql -h localhost -U trading_os -d trading_os

# View tables
\dt

# Exit
\q
```

### Redis

```bash
# Connect to Redis
redis-cli

# Check connection
ping

# View keys
keys *

# Exit
exit
```

## 🤖 AI Service & Model Management

The Trading OS includes a built-in AI service running local LLM models for trading analysis.

### Quick AI Setup

```bash
# Start all services
docker-compose up -d

# Download models (choose one tier)
bash ai.sh download fast       # ~637MB (development)
bash ai.sh download balanced   # ~3-4GB per model (recommended)
bash ai.sh download quality    # ~3-4GB per model (research)

# Check model availability
bash ai.sh check

# Start AI service
bash ai.sh start balanced
```

### AI Performance Tiers

| Tier | Size | Speed | Best For |
|------|------|-------|----------|
| **Fast** | 637MB | Ultra-fast | Development/Testing |
| **Balanced** | 3-4GB each | Fast | Production trading |
| **Quality** | 3-4GB each | Good | Deep analysis |

### Manual Model Management

```bash
# Download models
bash ai.sh download balanced    # Recommended for production
bash ai.sh download fast        # For testing
bash ai.sh download quality     # For analysis
bash ai.sh download all         # All models

# Check status
bash ai.sh check                # Model availability
bash ai.sh status               # Service status
bash ai.sh logs                 # View logs

# Manage service
bash ai.sh start balanced       # Start with tier
bash ai.sh stop                 # Stop service
bash ai.sh restart quality      # Restart with new tier
```

### AI Endpoints

```bash
# Check service health
curl http://localhost:3008/health

# List available models
bash ai.sh models

# View model info
bash ai.sh check
```

### Models Storage

Downloaded models are saved locally to:
```
.data/ai_models/
```

## 📊 Combined Frontend + Backend

Start everything together from the Portfolio root directory:

```bash
# Terminal 1: Start backend services
cd Backend
docker-compose up

# Terminal 2: Start frontend
cd Portfolio
npm run dev
```

Frontend will be available at: http://localhost:3000
Backend services will be available on their respective ports

## 🔧 Configuration

### Environment Variables

Copy and edit `.env.example` to `.env`:

```bash
cp .env.example .env
```

### AI Configuration

Copy and edit `.env.ai.example` to `.env`:

```bash
cp .env.ai.example .env
```

Options:
```
AI_PERFORMANCE_TIER=full          # full, balanced, quality, fast
AI_AUTO_DOWNLOAD=true             # Auto-download models
AI_PRELOAD_MODELS=true            # Preload priority models
AI_MAX_MEMORY_GB=16               # Memory limit
```

## 🧪 Testing

### Run Tests

```bash
# Run all tests
pytest

# Run specific service tests
pytest tests/portfolio/

# Run with coverage
pytest --cov=services tests/
```

### Manual Testing

```bash
# Test all health endpoints
for port in 3001 3002 3003 3004 3005 3006 3007 3008 3009; do
  echo "Port $port:"
  curl -s http://localhost:$port/health | jq .
done
```

## 📝 Service Architecture

```
Trading OS Backend
├── PostgreSQL (port 5432)
├── Redis (port 6379)
│
├── Microservices
│   ├── Orchestrator (3001) - Agent orchestration (LLM)
│   ├── Strategy (3002) - Trading strategy generation
│   ├── Risk (3003) - Risk assessment & management
│   ├── Execution (3004) - Order execution
│   ├── Portfolio (3005) - Portfolio management & analytics
│   ├── Analytics (3006) - Data analytics & reporting
│   ├── Config (3007) - Service configuration
│   ├── Local AI (3008) - Local AI models
│   └── Data Ingestion (3009) - Market data ingestion
│
└── Data Layer
    ├── .data/postgres/ - PostgreSQL data
    ├── .data/redis/ - Redis data
    ├── .data/ai_models/ - Downloaded AI models
    └── .data/model_cache/ - Model cache
```

## 🐛 Troubleshooting

### Services Not Starting

```bash
# Check Docker is running
docker --version

# Check logs
docker-compose logs

# Rebuild images
docker-compose build --no-cache

# Start with verbose output
docker-compose up --verbose
```

### Port Already in Use

```bash
# Find process using port
lsof -i :3001

# Kill process
kill -9 <PID>
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose logs postgres

# Test connection
psql -h localhost -U trading_os -d trading_os -c "SELECT 1"
```

### AI Service Issues

```bash
# Check AI service logs
docker-compose logs local_ai

# Restart AI service
docker-compose restart local_ai

# Clear models and restart
rm -rf .data/ai_models .data/model_cache
docker-compose restart local_ai
```

## 📚 Documentation

- [ai.sh](ai.sh) - AI model management script
- [Docker Compose Configuration](docker-compose.yml)
- [Service Details](services/)
- [Tests](tests/)

## 🔐 Security Notes

- Local development only - all services use dev credentials
- Enable authentication in production
- Secure API keys in `.env.local`
- Use HTTPS in production
## 📄 License

Part of Trading OS - All rights reserved