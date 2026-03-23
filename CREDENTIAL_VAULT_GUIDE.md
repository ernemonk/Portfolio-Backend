# 🔐 Credential Vault Guide

## Overview

The Trading OS uses a centralized, encrypted credential vault for managing all API keys, secrets, and passwords. All credentials are:
- **Encrypted** with AES-256 Fernet encryption before storage
- **Stored** in PostgreSQL database (persists in `.data/postgres`)
- **Managed** via web UI at [http://localhost:3000/portal/trading/data_ingestion](http://localhost:3000/portal/trading/data_ingestion)
- **Fetched** programmatically by services using the vault client API

## Architecture

```
┌─────────────────┐
│   Frontend UI   │  ← Add/View/Delete credentials
│  (port 3000)    │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Data Ingestion  │  ← Vault API (port 3009)
│   Service       │  ← Encryption/Decryption
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │  ← Encrypted storage
│  (port 5432)    │  ← api_credentials table
└─────────────────┘
         ↑
         │
┌─────────────────┐
│ Other Services  │  ← Fetch credentials via vault_client
│ (orchestrator,  │  ← Use decrypted values
│  execution, etc)│
└─────────────────┘
```

## Quick Start

### 1. Set Vault Master Key

The vault uses a master encryption key defined in `.env.local`:

```bash
# Backend/.env.local
VAULT_MASTER_KEY=your-secure-master-key-change-me-in-production
```

⚠️ **IMPORTANT**: Change this key in production! This key encrypts all credentials.

### 2. Start Services

```bash
cd Backend
docker compose up -d
```

### 3. Access Vault UI

Navigate to [http://localhost:3000/portal/trading/data_ingestion](http://localhost:3000/portal/trading/data_ingestion)

### 4. Add Credentials

Click **"+ Add Credential"** and fill in:
- **Provider Name**: e.g., `binance`, `anthropic`, `aws`
- **Credential Key**: e.g., `api_key`, `api_secret`, `access_token`
- **Value**: Your actual secret (will be encrypted)
- **Type**: `api_key`, `api_secret`, `password`, `token`, `oauth`, `other`
- **Label**: Optional description (e.g., "Production API Key")

## Using Credentials in Services

### Python Services (Async)

```python
from trading_os.security.vault_client import VaultClient

async def get_binance_credentials():
    async with VaultClient() as vault:
        api_key = await vault.get_credential("binance", "api_key")
        api_secret = await vault.get_credential("binance", "api_secret")
        return api_key, api_secret

# Or one-off fetch
from trading_os.security.vault_client import get_credential

api_key = await get_credential("anthropic", "api_key")
```

### Environment Variables

Configure services to use vault URL in `.env.local`:

```bash
DATA_INGESTION_URL=http://localhost:3009
```

## Vault API Endpoints

### POST /credentials
Store a new encrypted credential.

**Request:**
```json
{
  "provider_name": "binance",
  "credential_key": "api_key",
  "value": "your-secret-key",
  "credential_type": "api_key",
  "label": "Production Key"
}
```

**Response:**
```json
{
  "status": "stored",
  "provider": "binance"
}
```

### GET /credentials
List all credentials (without encrypted values).

**Query Parameters:**
- `provider_name` (optional): Filter by provider
- `credential_key` (optional): Filter by key

**Response:**
```json
[
  {
    "id": 1,
    "provider_name": "binance",
    "credential_key": "api_key",
    "credential_type": "api_key",
    "label": "Production Key",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

### GET /credentials/{id}/decrypt
Decrypt and return credential value.

⚠️ **WARNING**: Returns plaintext secrets. Use with caution.

**Response:**
```json
{
  "id": 1,
  "provider_name": "binance",
  "credential_key": "api_key",
  "value": "your-secret-key",
  "credential_type": "api_key"
}
```

### DELETE /credentials/{id}
Delete a credential.

**Response:**
```json
{
  "status": "deleted"
}
```

### GET /vault/status
Get vault statistics.

**Response:**
```json
{
  "total_credentials": 12,
  "active_credentials": 11,
  "providers": ["binance", "anthropic", "aws"],
  "vault_initialized": true
}
```

## Security Best Practices

### 🔒 Production Deployment

1. **Generate Strong Master Key**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Store in Secure Secret Manager**
   - AWS Secrets Manager
   - Azure Key Vault
   - HashiCorp Vault
   - Kubernetes Secrets

3. **Rotate Master Key Periodically**
   ```python
   from trading_os.security.vault import APIKeyVault
   
   vault = APIKeyVault()
   # Get all encrypted values from database
   encrypted_values = [...]  # Query from DB
   
   # Rotate to new key
   new_encrypted = vault.rotate_key("new-master-key", encrypted_values)
   # Update database with new encrypted values
   ```

4. **Restrict Network Access**
   - Vault API should only be accessible from internal network
   - Use firewall rules or security groups
   - Consider mutual TLS for service-to-service communication

5. **Audit Access**
   - Log all credential access attempts
   - Monitor for unusual patterns
   - Set up alerts for unauthorized access

### 🚫 What NOT to Do

- ❌ Don't commit `.env.local` to git (already in `.gitignore`)
- ❌ Don't store plaintext credentials anywhere
- ❌ Don't share vault master key via email/chat
- ❌ Don't use default master key in production
- ❌ Don't expose vault API to public internet

## Database Schema

Credentials are stored in the `api_credentials` table:

```sql
CREATE TABLE api_credentials (
    id SERIAL PRIMARY KEY,
    provider_name VARCHAR(100) NOT NULL,
    credential_key VARCHAR(100) NOT NULL,
    encrypted_value TEXT NOT NULL,  -- AES-256 encrypted
    credential_type VARCHAR(50) NOT NULL,
    label VARCHAR(200),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (provider_name, credential_key)
);
```

## Encryption Details

- **Algorithm**: AES-256 via Fernet (symmetric encryption)
- **Key Derivation**: SHA-256 hash of master passphrase
- **Library**: Python `cryptography` package
- **Format**: URL-safe base64-encoded ciphertext

### How It Works

1. **Encryption**:
   ```python
   master_key = "your-master-key"
   key_hash = hashlib.sha256(master_key.encode()).digest()
   fernet = Fernet(base64.urlsafe_b64encode(key_hash))
   ciphertext = fernet.encrypt(plaintext.encode())
   ```

2. **Decryption**:
   ```python
   plaintext = fernet.decrypt(ciphertext).decode()
   ```

## Migration from Environment Variables

### Old Way (.env files)
```bash
# Backend/.env
BINANCE_API_KEY=your-key
BINANCE_API_SECRET=your-secret
ANTHROPIC_API_KEY=your-key
```

### New Way (Vault)

1. **Add credentials via UI**:
   - Navigate to Data Ingestion service page
   - Click "+ Add Credential"
   - Enter each credential

2. **Update service code**:
   ```python
   # Before
   BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
   
   # After
   from trading_os.security.vault_client import get_credential
   BINANCE_API_KEY = await get_credential("binance", "api_key")
   ```

3. **Remove from .env.local**:
   - Delete plaintext credential lines
   - Keep only vault master key

## Troubleshooting

### Error: "Vault master key not set"

**Solution**: Set `VAULT_MASTER_KEY` in `.env.local`:
```bash
VAULT_MASTER_KEY=your-secure-key
```

### Error: "Credential not found"

**Solution**: Verify credential exists in UI or check spelling:
```python
# List all credentials
async with VaultClient() as vault:
    creds = await vault.list_credentials("binance")
    print(creds)
```

### Error: "Failed to decrypt"

**Solution**: Vault master key may have changed. If you rotated the key, update all encrypted values:
```python
vault.rotate_key(new_key, old_encrypted_values)
```

### Data Ingestion Service Unhealthy

**Solution**: Check if PostgreSQL is running:
```bash
docker compose ps postgres
docker compose logs data_ingestion
```

## Development vs Production

### Development
- Use default master key (already in `.env.local`)
- Add test credentials via UI
- Data persists in `.data/postgres` directory

### Production
- **Generate** strong master key
- **Store** master key in secure secret manager
- **Inject** master key as environment variable
- **Restrict** network access to vault API
- **Enable** audit logging
- **Backup** PostgreSQL database regularly
- **Test** credential rotation procedures

## Example: Complete Setup

```bash
# 1. Generate master key
VAULT_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Update .env.local
echo "VAULT_MASTER_KEY=$VAULT_KEY" >> Backend/.env.local

# 3. Start services
cd Backend
docker compose up -d

# 4. Wait for services to be healthy
docker compose ps

# 5. Add credentials via UI
open http://localhost:3000/portal/trading/data_ingestion

# 6. Test credential fetch
python -c "
import asyncio
from trading_os.security.vault_client import get_credential

async def test():
    key = await get_credential('binance', 'api_key')
    print(f'Fetched key: {key[:10]}...')

asyncio.run(test())
"
```

## Support

For issues or questions:
- Check service logs: `docker compose logs data_ingestion`
- Verify health: `curl http://localhost:3009/health`
- Check vault status: `curl http://localhost:3009/vault/status`
- Review this guide: `Backend/CREDENTIAL_VAULT_GUIDE.md`
