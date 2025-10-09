## Salesforce Pub/Sub Client (Azure Functions)

Minimal timer-triggered Azure Function that authenticates to Salesforce via JWT, fetches recent events by CreatedDate, stores them in SQLite, and uploads the DB to Azure Blob Storage.

### Prerequisites
- Python 3.10+
- Azure Functions Core Tools v4 (`func`)
- Azure CLI (`az`)
- Optional: Azurite (or use `UseDevelopmentStorage=true` which is set in `local.settings.example.json`)

### Setup (local)
1) Create venv and install deps
```bash
cd /Users/pradeep/projects/sandbox/salesforce_client
bash scripts/setup_venv.sh
```

2) Create local settings and fill values
```bash
cp local.settings.example.json local.settings.json
```

3) Add your Salesforce private key
```bash
# Put your key file here
ls certs/private.key
```

4) Optionally, set `.env` values (same keys as `local.settings.json`)
```bash
cp .env.example .env
```

### Launch function (local)
1) Start the local host
```bash
source .venv/bin/activate
func start
```

The timer trigger runs every 30 minutes. Logs show fetched event count and blob upload path.

### Invoke timer now (local)
To run immediately without waiting for the schedule, call the local admin endpoint:
```bash
curl -X POST http://localhost:7071/admin/functions/TimerPoller -H 'Content-Type: application/json' -d '{}'
```

### Deploy (Functions Core Tools)
1) Login
```bash
az login
```

2) Create (one-time) Azure resources
```bash
az group create -n <rg> -l <region>
az storage account create -n <storageName> -g <rg> -l <region> --sku Standard_LRS
az functionapp create -g <rg> -n <appName> -s <storageName> \
  --consumption-plan-location <region> --runtime python --functions-version 4
```

3) Configure app settings (example)
```bash
az functionapp config appsettings set -g <rg> -n <appName> --settings \
  SF_CLIENT_ID=<id> SF_USERNAME=<email> SF_LOGIN_URL=https://login.salesforce.com \
  SF_AUDIENCE=https://login.salesforce.com SF_PRIVATE_KEY_PATH=certs/private.key \
  SF_TOPIC_NAMES=/event/Delete_Logs__e \
  AZURE_STORAGE_CONNECTION_STRING='<conn_str>' AZURE_BLOB_CONTAINER=events \
  SQLITE_DB_DIR=data
```

4) Publish
```bash
func azure functionapp publish <appName> --python
```

### Minimal code reference
- `src/functions/TimerPoller/__init__.py`: Orchestrates run (auth → fetch → write → upload → save cursor).
- `src/app/config/settings.py`: Loads settings from env/local.settings.
- `src/app/salesforce/auth.py`: JWT assertion and OAuth token exchange.
- `src/app/salesforce/events.py`: Simple SOQL paging by CreatedDate.
- `src/app/replay/cursor_store.py`: Per-topic ISO timestamp cursor in SQLite.
- `src/app/storage/sqlite_writer.py`: Writes events to `events_YYYYMMDDTHHMMSSZ.db`.
- `src/app/storage/azure_blob.py`: Uploads DB file to blob `events/`.

### Environment keys
- `SF_CLIENT_ID`, `SF_USERNAME`, `SF_LOGIN_URL`, `SF_AUDIENCE`, `SF_PRIVATE_KEY_PATH`, `SF_TOPIC_NAMES`
- `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_BLOB_CONTAINER`
- `SQLITE_DB_DIR`