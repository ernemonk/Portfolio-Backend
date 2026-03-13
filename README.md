# Trading OS Backend Services

Complete backend microservices for the Trading OS platform with PostgreSQL, Redis, and AI integration.

# Terminal 1: Backend
cd Backend && docker-compose up -d

# Terminal 2: Frontend
cd Portfolio && npm install && npm run dev

# Browser
open http://localhost:3000

## 🚀 Quick Start

### Start All Backend Services (with Docker Compose)

```bash
# From Backend directory
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

This starts all 7 services in parallel:
- **PostgreSQL** (port 5432)
- **Redis** (port 6379)
- **Portfolio Service** (port 3001)
- **Strategy Service** (port 3002)
- **Risk Service** (port 3003)
- **Execution Service** (port 3004)
- **Orchestrator Service** (port 3005)
- **Analytics Service** (port 3006)
- **Config Service** (port 3007)
- **Local AI Service** (port 3008)

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
curl http://localhost:3001/health    # Portfolio
curl http://localhost:3002/health    # Strategy
curl http://localhost:3003/health    # Risk
curl http://localhost:3004/health    # Execution
curl http://localhost:3005/health    # Orchestrator
curl http://localhost:3006/health    # Analytics
curl http://localhost:3007/health    # Config
curl http://localhost:3008/health    # AI Service
```

## 🔗 Service URLs

| Service | Port | Health Check |
|---------|------|--------------|
| Portfolio | 3001 | http://localhost:3001/health |
| Strategy | 3002 | http://localhost:3002/health |
| Risk | 3003 | http://localhost:3003/health |
| Execution | 3004 | http://localhost:3004/health |
| Orchestrator | 3005 | http://localhost:3005/health |
| Analytics | 3006 | http://localhost:3006/health |
| Config | 3007 | http://localhost:3007/health |
| Local AI | 3008 | http://localhost:3008/health |
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

## 🤖 AI Service

### Start AI Service with All Models

```bash
cd Backend
./elegant-ai-setup.sh
```

This will:
- Start the local AI service
- Auto-download all models
- Enable smart model selection for trading tasks

### AI Endpoints

```bash
# Get available models
curl http://localhost:3008/dashboard/models

# Select model for task
curl -X POST http://localhost:3008/dashboard/select-model \
  -H "Content-Type: application/json" \
  -d '{"task_type": "real_time_trading", "prefer_speed": true}'

# Send smart chat message
curl -X POST http://localhost:3008/v1/chat/completions/smart \
  -H "Content-Type: application/json" \
  -d '{
    "model": "auto-select",
    "messages": [{"role": "user", "content": "Analyze AAPL"}],
    "task_type": "financial_analysis",
    "prefer_speed": false
  }'
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
for port in 3001 3002 3003 3004 3005 3006 3007 3008; do
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
│   ├── Portfolio (3001) - Portfolio management & analytics
│   ├── Strategy (3002) - Trading strategy generation
│   ├── Risk (3003) - Risk assessment & management
│   ├── Execution (3004) - Order execution
│   ├── Orchestrator (3005) - Agent orchestration (LLM)
│   ├── Analytics (3006) - Data analytics & reporting
│   ├── Config (3007) - Service configuration
│   └── Local AI (3008) - Local AI models
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

- [Docker Compose Configuration](docker-compose.yml)
- [AI Service Setup](elegant-ai-setup.sh)
- [Service Details](services/)

## 🔐 Security Notes

- Local development only - all services use dev credentials
- Enable authentication in production
- Secure API keys in `.env.local`
- Use HTTPS in production

## 📄 License

Part of Trading OS - All rights reserved