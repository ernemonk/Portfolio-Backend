"""
Configuration Service  -  port 3007

Responsibilities:
  - Store and manage system-wide configuration settings
  - Provide REST API for reading/writing config from UI
  - Generate environment files and docker-compose updates
  - Validate configuration changes before applying
  - Track configuration history and rollback support

Configuration Categories:
  - Database connections (PostgreSQL, Redis)
  - Exchange credentials and settings
  - LLM provider configurations  
  - Service-level settings (ports, queue backend)
  - Pricing data source settings
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, update, delete, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from trading_os.db.database import get_session, create_all_tables
from trading_os.db.models import APICredential, DataSource
from trading_os.security.vault import APIKeyVault

# ---------------------------------------------------------------------------
# Configuration Models
# ---------------------------------------------------------------------------

class DatabaseConfig(BaseModel):
    postgresql: Dict[str, Any]
    redis: Dict[str, Any]

class ExchangeConfig(BaseModel):
    activeExchange: str
    paperMode: bool
    credentials: Dict[str, Dict[str, Any]]

class LLMProvider(BaseModel):
    name: str
    displayName: str
    fields: Dict[str, str]  # Completely dynamic fields

class LLMConfig(BaseModel):
    provider: str
    providers: Dict[str, LLMProvider]

class ServiceConfig(BaseModel):
    executionQueueBackend: str
    environment: str
    ports: Dict[str, int]

class PricingConfig(BaseModel):
    provider: str
    apiKey: Optional[str] = None
    updateInterval: int
    cacheTtl: int

class BackendConfiguration(BaseModel):
    database: DatabaseConfig
    exchanges: ExchangeConfig
    llm: LLMConfig
    service: ServiceConfig
    pricing: PricingConfig
    lastUpdated: datetime

class ConfigUpdate(BaseModel):
    section: str
    data: Dict[str, Any]

class HealthCheck(BaseModel):
    status: str
    timestamp: float
    service: str = "config"


class CredentialInput(BaseModel):
    provider_name: str
    credential_key: str
    value: str  # plaintext — will be encrypted
    credential_type: str = "api_key"
    label: Optional[str] = None


class CredentialUpdate(BaseModel):
    value: Optional[str] = None
    label: Optional[str] = None
    is_active: Optional[bool] = None


# ── Encryption Vault ──────────────────────────────────────────────────────
vault = APIKeyVault()


# ---------------------------------------------------------------------------
# Application Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Trading OS - Configuration Service",
    description="Centralized configuration management for Trading OS backend services",
    version="1.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Configuration Storage
# ---------------------------------------------------------------------------

# In-memory storage (production would use persistent database)
_config_store: Optional[BackendConfiguration] = None
_config_history: list[BackendConfiguration] = []

def get_default_config() -> BackendConfiguration:
    """Return default configuration"""
    return BackendConfiguration(
        database=DatabaseConfig(
            postgresql={
                "host": "localhost",
                "port": 5432,
                "database": "trading_os", 
                "username": "trading_os",
                "password": "trading_os_dev",
                "connectionString": "postgresql+asyncpg://trading_os:trading_os_dev@localhost:5432/trading_os"
            },
            redis={
                "host": "localhost",
                "port": 6379,
                "password": None,
                "url": "redis://localhost:6379"
            }
        ),
        exchanges=ExchangeConfig(
            activeExchange="paper",
            paperMode=True,
            credentials={
                "binance": {"apiKey": "", "apiSecret": "", "sandbox": True},
                "kraken": {"apiKey": "", "apiSecret": ""},
                "coinbase": {"apiKey": "", "apiSecret": ""},
                "alpaca": {"apiKey": "", "apiSecret": "", "baseUrl": "https://paper-api.alpaca.markets"}
            }
        ),
        llm=LLMConfig(
            provider="mock",
            providers={
                "mock": LLMProvider(
                    name="mock",
                    displayName="Mock (Free, Local Testing)", 
                    fields={}
                ),
                "anthropic": LLMProvider(
                    name="anthropic", 
                    displayName="Anthropic Claude",
                    fields={
                        "apiKey": "",
                        "model": "claude-3.5-sonnet",
                        "baseUrl": "https://api.anthropic.com"
                    }
                ),
                "openai": LLMProvider(
                    name="openai",
                    displayName="OpenAI GPT", 
                    fields={
                        "apiKey": "",
                        "model": "gpt-4o",
                        "baseUrl": "https://api.openai.com"
                    }
                )
            }
        ),
        service=ServiceConfig(
            executionQueueBackend="memory",
            environment="development",
            ports={
                "portfolio": 3001,
                "strategy": 3002,
                "risk": 3003,
                "execution": 3004,
                "orchestrator": 3005,
                "analytics": 3006,
                "config": 3007,
                "data_ingestion": 3009
            }
        ),
        pricing=PricingConfig(
            provider="coingecko",
            updateInterval=300,
            cacheTtl=300
        ),
        lastUpdated=datetime.now()
    )

def load_config() -> BackendConfiguration:
    """Load configuration from storage"""
    global _config_store
    if _config_store is None:
        # Try to load from file, fallback to defaults
        config_file = Path("config.json")
        if config_file.exists():
            try:
                with open(config_file) as f:
                    data = json.load(f)
                    # Convert ISO string back to datetime
                    data["lastUpdated"] = datetime.fromisoformat(data["lastUpdated"])
                    _config_store = BackendConfiguration(**data)
            except Exception as e:
                print(f"Failed to load config file: {e}, using defaults")
                _config_store = get_default_config()
        else:
            _config_store = get_default_config()
    return _config_store

def save_config(config: BackendConfiguration) -> None:
    """Save configuration to storage"""
    global _config_store, _config_history
    
    # Add current config to history before updating
    if _config_store:
        _config_history.append(_config_store)
        # Keep only last 10 versions
        _config_history = _config_history[-10:]
    
    _config_store = config
    
    # Save to file
    config_file = Path("config.json")
    try:
        # Convert datetime to ISO string for JSON serialization
        data = config.dict()
        data["lastUpdated"] = config.lastUpdated.isoformat()
        with open(config_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Failed to save config file: {e}")

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint"""
    return HealthCheck(status="ok", timestamp=time.time())

@app.get("/config", response_model=BackendConfiguration)
async def get_config():
    """Get current configuration"""
    return load_config()

@app.post("/config", response_model=BackendConfiguration)
async def update_config(config: BackendConfiguration):
    """Update configuration"""
    config.lastUpdated = datetime.now()
    save_config(config)
    await apply_config_changes(config)
    return config

@app.patch("/config/{section}")
async def update_config_section(section: str, data: Dict[str, Any]):
    """Update a specific configuration section"""
    config = load_config()
    
    if not hasattr(config, section):
        raise HTTPException(status_code=400, detail=f"Unknown config section: {section}")
    
    # Update the section
    current_section = getattr(config, section)
    if hasattr(current_section, 'dict'):
        # Pydantic model - merge the data
        updated_data = {**current_section.dict(), **data}
        section_model = type(current_section)(**updated_data)
        setattr(config, section, section_model)
    else:
        # Direct assignment
        setattr(config, section, data)
    
    config.lastUpdated = datetime.now()
    save_config(config)
    await apply_config_changes(config)
    return {"status": "updated", "section": section}

@app.get("/config/history")
async def get_config_history():
    """Get configuration change history"""
    return {"history": [{"lastUpdated": cfg.lastUpdated, "version": i+1} for i, cfg in enumerate(_config_history)]}

@app.post("/config/rollback/{version}")
async def rollback_config(version: int):
    """Rollback to a previous configuration version"""
    if version < 1 or version > len(_config_history):
        raise HTTPException(status_code=400, detail="Invalid version number")
    
    config = _config_history[version - 1]
    config.lastUpdated = datetime.now()
    save_config(config)
    await apply_config_changes(config)
    return {"status": "rolled back", "version": version}

@app.get("/config/env")
async def generate_env_file():
    """Generate .env file content from current configuration"""
    config = load_config()
    
    env_lines = [
        "# ─── Generated from Trading OS Config Center ───────────────────────",
        f"# Generated: {datetime.now().isoformat()}",
        "",
        "# ─── Database ──────────────────────────────────────────────────────",
        f"DATABASE_URL={config.database.postgresql['connectionString']}",
        f"REDIS_URL={config.database.redis['url']}",
        "",
        "# ─── Exchange ──────────────────────────────────────────────────────",
        f"PAPER_MODE={str(config.exchanges.paperMode).lower()}",
        f"EXCHANGE_ID={config.exchanges.activeExchange}",
    ]
    
    # Add exchange credentials
    for exchange, creds in config.exchanges.credentials.items():
        env_lines.extend([
            f"{exchange.upper()}_API_KEY={creds.get('apiKey', '')}",
            f"{exchange.upper()}_API_SECRET={creds.get('apiSecret', '')}"
        ])
    
    env_lines.extend([
        "",
        "# ─── LLM Provider ─────────────────────────────────────────────────",
        f"MODEL_PROVIDER={config.llm.provider}",
    ])
    
    # Add all configured LLM providers
    for provider_name, provider_config in config.llm.providers.items():
        # Add all dynamic fields for this provider
        for field_name, field_value in provider_config.fields.items():
            env_lines.append(f"{provider_name.upper()}_{field_name.upper()}={field_value}")
    
    env_lines.extend([
        "",
        "# ─── Service Config ───────────────────────────────────────────────",
        f"EXECUTION_QUEUE_BACKEND={config.service.executionQueueBackend}",
        f"ENV={config.service.environment}",
        ""
    ])
    
    return {"content": "\\n".join(env_lines)}

@app.get("/config/validate")
async def validate_config():
    """Validate current configuration"""
    config = load_config()
    issues = []
    
    # Check database connections
    try:
        if not config.database.postgresql['connectionString']:
            issues.append("PostgreSQL connection string is empty")
        if not config.database.redis['url']:
            issues.append("Redis URL is empty")
    except KeyError as e:
        issues.append(f"Missing database config: {e}")
    
    # Check exchange credentials if not in paper mode
    if not config.exchanges.paperMode:
        active_exchange = config.exchanges.activeExchange
        if active_exchange in config.exchanges.credentials:
            creds = config.exchanges.credentials[active_exchange]
            if not creds.get('apiKey'):
                issues.append(f"Missing API key for active exchange: {active_exchange}")
            if not creds.get('apiSecret'):
                issues.append(f"Missing API secret for active exchange: {active_exchange}")
        else:
            issues.append(f"No credentials configured for active exchange: {active_exchange}")
    
    # Check LLM provider
    if config.llm.provider != "mock":
        if config.llm.provider in config.llm.providers:
            provider = config.llm.providers[config.llm.provider]
            # Check if provider has an apiKey field and if it's empty
            if 'apiKey' in provider.fields and not provider.fields['apiKey']:
                issues.append(f"API key required for {provider.displayName} provider")
        else:
            issues.append(f"Selected provider '{config.llm.provider}' is not configured")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "timestamp": datetime.now()
    }

@app.post("/config/test-connection")
async def test_connection(service: str):
    """Test connection to a specific service or database"""
    config = load_config()
    
    try:
        if service == "postgresql":
            # In production, would actually test DB connection
            # For now, just check if config exists
            pg_config = config.database.postgresql
            if pg_config['connectionString']:
                return {"status": "ok", "message": "PostgreSQL config validated"}
            else:
                return {"status": "error", "message": "Missing PostgreSQL connection string"}
                
        elif service == "redis":
            # Test Redis connection
            redis_config = config.database.redis
            redis_client = aioredis.from_url(redis_config['url'])
            await redis_client.ping()
            await redis_client.close()
            return {"status": "ok", "message": "Redis connection successful"}
            
        elif service in ["portfolio", "strategy", "risk", "execution", "orchestrator", "analytics"]:
            # Test service health
            port = config.service.ports.get(service)
            if not port:
                return {"status": "error", "message": f"No port configured for {service}"}
            
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://localhost:{port}/health", timeout=5.0)
                if response.status_code == 200:
                    return {"status": "ok", "message": f"{service} service healthy"}
                else:
                    return {"status": "error", "message": f"{service} service returned {response.status_code}"}
        else:
            return {"status": "error", "message": f"Unknown service: {service}"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Encrypted Credential Vault (stored in PostgreSQL)
# ---------------------------------------------------------------------------

@app.get("/credentials")
async def list_credentials(db: AsyncSession = Depends(get_session)):
    """List all stored API credentials (values are never returned)."""
    result = await db.execute(
        select(APICredential).order_by(APICredential.provider_name)
    )
    creds = result.scalars().all()
    return [
        {
            "id": c.id,
            "provider_name": c.provider_name,
            "credential_key": c.credential_key,
            "credential_type": c.credential_type,
            "label": c.label,
            "is_active": c.is_active,
            "is_set": bool(c.encrypted_value),
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
            "last_verified_at": c.last_verified_at.isoformat() if c.last_verified_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in creds
    ]


@app.post("/credentials")
async def store_credential(
    cred: CredentialInput, db: AsyncSession = Depends(get_session)
):
    """Store or update an encrypted API credential."""
    encrypted = vault.encrypt(cred.value)

    # Upsert: check if credential already exists for this provider+key
    result = await db.execute(
        select(APICredential).where(
            APICredential.provider_name == cred.provider_name,
            APICredential.credential_key == cred.credential_key,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_value = encrypted
        existing.credential_type = cred.credential_type
        existing.label = cred.label
        existing.updated_at = datetime.now(timezone.utc)
        cred_id = existing.id
    else:
        new_cred = APICredential(
            provider_name=cred.provider_name,
            credential_key=cred.credential_key,
            encrypted_value=encrypted,
            credential_type=cred.credential_type,
            label=cred.label,
        )
        db.add(new_cred)
        await db.flush()
        cred_id = new_cred.id

    await db.commit()
    return {"status": "stored", "id": cred_id, "provider": cred.provider_name}


@app.put("/credentials/{credential_id}")
async def update_credential(
    credential_id: int,
    update_data: CredentialUpdate,
    db: AsyncSession = Depends(get_session),
):
    """Update an existing credential."""
    result = await db.execute(
        select(APICredential).where(APICredential.id == credential_id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    if update_data.value is not None:
        cred.encrypted_value = vault.encrypt(update_data.value)
    if update_data.label is not None:
        cred.label = update_data.label
    if update_data.is_active is not None:
        cred.is_active = update_data.is_active

    cred.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "updated", "id": credential_id}


@app.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: int, db: AsyncSession = Depends(get_session)
):
    """Delete a stored credential."""
    result = await db.execute(
        select(APICredential).where(APICredential.id == credential_id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    await db.execute(
        delete(APICredential).where(APICredential.id == credential_id)
    )
    await db.commit()
    return {"status": "deleted", "id": credential_id}


@app.post("/credentials/verify/{credential_id}")
async def verify_credential(
    credential_id: int, db: AsyncSession = Depends(get_session)
):
    """Verify a credential can be decrypted (does not reveal value)."""
    result = await db.execute(
        select(APICredential).where(APICredential.id == credential_id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    try:
        decrypted = vault.decrypt(cred.encrypted_value)
        cred.last_verified_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "status": "ok",
            "message": "Credential decrypted successfully",
            "length": len(decrypted),
            "preview": decrypted[:4] + "..." if len(decrypted) > 4 else "***",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.post("/credentials/{credential_id}/decrypt")
async def decrypt_credential(
    credential_id: int, db: AsyncSession = Depends(get_session)
):
    """Decrypt and return the actual credential value (for frontend UI)."""
    result = await db.execute(
        select(APICredential).where(APICredential.id == credential_id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    try:
        decrypted = vault.decrypt(cred.encrypted_value)
        cred.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "status": "ok",
            "id": credential_id,
            "provider_name": cred.provider_name,
            "credential_key": cred.credential_key,
            "decrypted_value": decrypted,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to decrypt credential: {str(exc)}"
        )


# ---------------------------------------------------------------------------
# Vault Status
# ---------------------------------------------------------------------------

@app.get("/vault/status")
async def vault_status(db: AsyncSession = Depends(get_session)):
    """Return vault overview: total credentials, active count, encryption algo."""
    result = await db.execute(select(APICredential))
    creds = result.scalars().all()
    active = sum(1 for c in creds if c.is_active)
    return {
        "total_credentials": len(creds),
        "active_credentials": active,
        "encryption": "AES-256-Fernet",
        "vault_key_set": bool(os.getenv("VAULT_MASTER_KEY")),
    }


# ---------------------------------------------------------------------------
# Database Browser (shared PostgreSQL introspection)
# ---------------------------------------------------------------------------

@app.get("/database/tables")
async def list_database_tables(db: AsyncSession = Depends(get_session)):
    """List all tables in the database with row counts."""
    query = text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """)
    result = await db.execute(query)
    table_names = [row[0] for row in result.fetchall()]

    tables_info = []
    for table_name in table_names:
        try:
            count_result = await db.execute(
                text(f'SELECT COUNT(*) FROM "{table_name}"')
            )
            row_count = count_result.scalar() or 0
        except Exception:
            row_count = 0
        tables_info.append({"table_name": table_name, "row_count": row_count})

    return tables_info


@app.get("/database/tables/{table_name}/schema")
async def get_table_schema(
    table_name: str, db: AsyncSession = Depends(get_session)
):
    """Get column-level schema information for a table."""
    query = text("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
        ORDER BY ordinal_position;
    """)
    result = await db.execute(query, {"table_name": table_name})
    columns = result.fetchall()
    return [
        {
            "column_name": row[0],
            "data_type": row[1],
            "is_nullable": row[2] == "YES",
            "default_value": row[3],
        }
        for row in columns
    ]


@app.get("/database/tables/{table_name}/data")
async def get_table_data(
    table_name: str,
    page: int = 1,
    page_size: int = 25,
    search: Optional[str] = None,
    search_column: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    """Paginated table data with optional column search."""
    # Validate table exists (prevent SQL injection via table_name)
    exists = await db.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :table_name
            )
        """),
        {"table_name": table_name},
    )
    if not exists.scalar():
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    offset = (page - 1) * page_size

    # Total row count
    total_rows = (
        await db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
    ).scalar()

    # Fetch rows with optional search filter
    if search and search_column:
        col_check = await db.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = :table_name
                      AND column_name = :column_name
                )
            """),
            {"table_name": table_name, "column_name": search_column},
        )
        if not col_check.scalar():
            raise HTTPException(
                status_code=400, detail=f"Column '{search_column}' not found"
            )
        result = await db.execute(
            text(f"""
                SELECT * FROM "{table_name}"
                WHERE CAST("{search_column}" AS TEXT) ILIKE :search
                ORDER BY 1 DESC
                LIMIT :limit OFFSET :offset
            """),
            {"search": f"%{search}%", "limit": page_size, "offset": offset},
        )
    else:
        result = await db.execute(
            text(
                f'SELECT * FROM "{table_name}" ORDER BY 1 DESC LIMIT :limit OFFSET :offset'
            ),
            {"limit": page_size, "offset": offset},
        )

    rows = result.fetchall()
    columns = result.keys()

    data = [
        {
            col: (val.isoformat() if hasattr(val, "isoformat") else val)
            for col, val in zip(columns, row)
        }
        for row in rows
    ]

    return {
        "table_name": table_name,
        "total_rows": total_rows,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_rows + page_size - 1) // page_size,
        "columns": list(columns),
        "data": data,
    }


# ---------------------------------------------------------------------------
# Data Source Configuration (mirrors data_ingestion sources)
# ---------------------------------------------------------------------------

@app.get("/data-sources")
async def list_data_sources(db: AsyncSession = Depends(get_session)):
    """List all data source configurations."""
    result = await db.execute(select(DataSource).order_by(DataSource.name))
    sources = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "display_name": s.display_name,
            "provider_type": s.provider_type,
            "base_url": s.base_url,
            "requires_auth": s.requires_auth,
            "rate_limit_requests": s.rate_limit_requests,
            "rate_limit_period_seconds": s.rate_limit_period_seconds,
            "poll_interval_seconds": s.poll_interval_seconds,
            "status": s.status,
            "error_count": s.error_count,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "last_error_at": s.last_error_at.isoformat() if s.last_error_at else None,
            "enabled_pairs": s.enabled_pairs,
            "is_active": s.is_active,
        }
        for s in sources
    ]


@app.patch("/data-sources/{source_name}")
async def update_data_source(
    source_name: str, data: Dict[str, Any], db: AsyncSession = Depends(get_session)
):
    """Update data source configuration fields."""
    allowed_fields = {
        "rate_limit_requests", "rate_limit_period_seconds",
        "poll_interval_seconds", "enabled_pairs", "is_active",
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    await db.execute(
        update(DataSource).where(DataSource.name == source_name).values(**updates)
    )
    await db.commit()
    return {"status": "updated", "source": source_name}

# ---------------------------------------------------------------------------
# Configuration Application
# ---------------------------------------------------------------------------

async def apply_config_changes(config: BackendConfiguration):
    """Apply configuration changes to running services"""
    # In production, this would:
    # 1. Generate new environment files
    # 2. Update docker-compose.yml if needed  
    # 3. Restart affected services
    # 4. Notify services of config changes via Redis pub/sub
    
    print(f"Configuration updated at {config.lastUpdated}")
    
    # For now, just log the change
    print("Configuration changes applied")

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Initialize configuration service"""
    print("Starting Configuration Service on port 3007...")
    
    # Ensure DB tables exist (for credential vault)
    await create_all_tables()
    print("Database tables ensured for credential vault.")
    
    # Load initial configuration
    config = load_config()
    print(f"Loaded configuration last updated: {config.lastUpdated}")
    
    # Validate configuration on startup
    # validation = await validate_config()
    # if not validation["valid"]:
    #     print("WARNING: Configuration validation failed:", validation["issues"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3007)