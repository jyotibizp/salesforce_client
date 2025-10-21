# Salesforce Delete Event Tracker

Complete pipeline for tracking Salesforce delete events and syncing to Snowflake.

## System Overview

Two separate Azure Function apps that work together:

```
Salesforce → salesforce_client → Azure Blob Storage → delete_sync → Snowflake
```

### 1. salesforce_client (Event Collector)
**Schedule:** Every 30 minutes  
**Purpose:** Fetch delete events from Salesforce and store in SQLite files

- Authenticates to Salesforce via JWT
- Subscribes to platform events via gRPC Pub/Sub API
- Decodes Avro payloads
- Stores events in timestamped SQLite files
- Uploads to Azure Blob Storage
- Maintains replay cursors for resumption

[→ Full documentation](./salesforce_client/README.md)

### 2. delete_sync (Snowflake Sync)
**Schedule:** Every 24 hours  
**Purpose:** Sync all SQLite files to Snowflake for analytics

- Lists all event files from Azure Blob Storage
- Downloads and reads SQLite databases
- Inserts events into Snowflake `delete_tracker` table
- Skips duplicates automatically
- **Supports RSA key authentication** (recommended for production)

[→ Full documentation](./delete_sync/README.md)  
[→ RSA Key Setup Guide](./delete_sync/docs/RSA_KEY_SETUP.md)

## Quick Start

### Setup salesforce_client
```bash
cd salesforce_client
bash scripts/setup_venv.sh
cp local.settings.example.json local.settings.json
# Edit local.settings.json with Salesforce credentials
source .venv/bin/activate
func start
```

### Setup delete_sync
```bash
cd delete_sync
bash scripts/setup_venv.sh
cp local.settings.example.json local.settings.json
# Edit local.settings.json with Snowflake credentials
source .venv/bin/activate
func start
```

## Architecture

```mermaid
graph LR
    SF[Salesforce<br/>Platform Events]
    SC[salesforce_client<br/>Azure Function<br/>Every 30 min]
    Blob[(Azure Blob Storage<br/>SQLite Files)]
    DS[delete_sync<br/>Azure Function<br/>Every 24 hours]
    Snow[(Snowflake<br/>delete_tracker)]
    
    SF -->|gRPC Pub/Sub| SC
    SC -->|Upload .db files| Blob
    Blob -->|Read all files| DS
    DS -->|Insert events| Snow
    
    style SC fill:#e1f5ff
    style DS fill:#fff3cd
    style Blob fill:#f8d7da
    style Snow fill:#d4edda
```

## Data Flow

1. **salesforce_client** polls Salesforce every 30 minutes
2. Fetches delete events via Pub/Sub API
3. Stores in `events_YYYYMMDDTHHMMSSZ.db` files
4. Uploads to Azure Blob Storage `events/` container
5. **delete_sync** runs once per day
6. Downloads all SQLite files from blob storage
7. Inserts events into Snowflake (skips duplicates)

## Storage Structure

### Azure Blob Storage
```
events/
├── events_20251021T103000Z.db
├── events_20251021T133000Z.db
├── events_20251021T163000Z.db
└── ...
```

### Snowflake Table
```sql
CREATE TABLE delete_tracker (
    id INTEGER PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE,
    topic VARCHAR(255),
    object_name VARCHAR(255),
    record_id VARCHAR(255),
    deleted_by VARCHAR(255),
    deleted_date TIMESTAMP_NTZ,
    owner_id VARCHAR(255),
    payload VARIANT,
    ingested_at TIMESTAMP_NTZ
);
```

## Configuration

### salesforce_client
- Salesforce credentials (JWT, Connected App)
- Azure Blob Storage connection
- Platform event topic names

### delete_sync
- Azure Blob Storage connection (same as above)
- Snowflake credentials (password OR RSA key)
- Target table configuration

**Authentication Options:**
- **Password authentication:** Simple, for dev/testing
- **RSA key authentication:** Recommended for production
  - More secure, no password storage
  - See [RSA Key Setup Guide](./delete_sync/docs/RSA_KEY_SETUP.md)

## Deployment

Both apps deploy independently to Azure:

```bash
# Deploy salesforce_client
cd salesforce_client
func azure functionapp publish <salesforce-app-name> --python

# Deploy delete_sync
cd delete_sync
func azure functionapp publish <snowflake-sync-app-name> --python
```

### Snowflake RSA Key Authentication (Production)

```bash
# 1. Generate key pair
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out snowflake_rsa_key.p8 -nocrypt
openssl rsa -in snowflake_rsa_key.p8 -pubout -out snowflake_rsa_key.pub

# 2. Assign public key to Snowflake user
# ALTER USER svc_account SET RSA_PUBLIC_KEY='...'

# 3. Store private key in Azure Key Vault
az keyvault secret set --vault-name <vault> --name snowflake-rsa-key --file snowflake_rsa_key.p8

# 4. Configure function
az functionapp config appsettings set -g <rg> -n <app-name> --settings \
  SNOWFLAKE_PRIVATE_KEY_PATH="@Microsoft.KeyVault(...)"
```

[→ Full RSA Key Setup Guide](./delete_sync/docs/RSA_KEY_SETUP.md)

## Testing

### Local Testing
1. Set `MOCK_MODE=true` in salesforce_client
2. Run salesforce_client to generate test SQLite files
3. Run delete_sync to sync to Snowflake
4. Query Snowflake to verify

### Production Monitoring
```sql
-- Check recent events
SELECT * FROM delete_tracker 
ORDER BY ingested_at DESC 
LIMIT 10;

-- Count by object type
SELECT object_name, COUNT(*) 
FROM delete_tracker 
GROUP BY object_name;

-- Events by day
SELECT DATE(ingested_at) as date, COUNT(*) 
FROM delete_tracker 
GROUP BY DATE(ingested_at)
ORDER BY date DESC;

-- Check connection history (RSA key auth)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE USER_NAME = 'SVC_DELETE_TRACKER'
  AND AUTHENTICATOR = 'RSA_KEYPAIR'
ORDER BY EVENT_TIMESTAMP DESC;
```

## Key Features

- **Replay capability:** Never miss events with cursor-based resumption
- **Duplicate prevention:** Events inserted once via `event_id` uniqueness
- **Secure authentication:** RSA key support for Snowflake (recommended for production)
- **Error resilience:** Both functions handle failures gracefully
- **Local development:** Mock mode for testing without Salesforce
- **Scalable:** Add topics or increase frequency without code changes
- **Auditable:** Full event history in Snowflake for analytics

## Technology Stack

- Azure Functions (Python 3.9+)
- Salesforce gRPC Pub/Sub API
- Avro serialization
- SQLite for intermediate storage
- Azure Blob Storage
- Snowflake data warehouse
- JWT authentication (Salesforce)
- RSA key authentication (Snowflake)

## Repository Structure

```
sf_delete_tracker/
├── salesforce_client/       # Event collector from Salesforce
│   ├── TimerPoller/         # Azure Function
│   ├── src/app/            # Application code
│   ├── requirements.txt
│   └── README.md
├── delete_sync/            # Snowflake sync
│   ├── SnowflakePusher/   # Azure Function
│   ├── src/                # Application code
│   ├── docs/
│   │   └── RSA_KEY_SETUP.md  # RSA key auth guide
│   ├── requirements.txt
│   └── README.md
└── README.md              # This file
```

## Security Best Practices

✅ **Recommended:**
- Use RSA key authentication for Snowflake in production
- Store private keys in Azure Key Vault
- Use service accounts (not personal users)
- Rotate keys regularly (every 90 days)
- Separate keys per environment (dev/staging/prod)
- Use JWT authentication for Salesforce

❌ **Avoid:**
- Password authentication in production
- Committing private keys to git
- Sharing keys between services
- Using personal user accounts for automation

