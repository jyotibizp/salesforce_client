# Debug Guide - No Events Received

## Protobuf Version Check ✅

**Result**: Protobuf files are IDENTICAL between continuous and batch mode:
- Both: Protobuf Python Version 6.31.1
- Both: gRPC 1.74.0
- Same DESCRIPTOR serialization

**Conclusion**: Protobuf version is NOT the issue.

---

## Comprehensive Debug Logging Added

I've added extensive logging to track the entire flow. When you run the TimerPoller now, you'll see:

### 1. Authentication Details
```
Using tenant_id: ...
Using instance_url: ...
Access token length: XXX chars
```

### 2. Connection Status
```
✓ Connected to Salesforce Pub/Sub API at api.pubsub.salesforce.com:7443
```

### 3. Topic Info
```
Retrieved topic info for /event/Delete_Logs__e: schema_id=...
```

### 4. Schema Fetch
```
Avro schema GET https://...salesforce.com/services/data/v64.0/event/eventSchema/... -> 200
Retrieved schema for schema_id=... via REST
Using schema for decoding: ...
```

### 5. Subscription Details
```
Subscribing to /event/Delete_Logs__e from EARLIEST (first run)
Starting Subscribe RPC call...
Subscribe RPC call established, waiting for response...
```

### 6. Response Details
```
Received fetch_response #1 from stream
latest_replay_id: 12345678 (length: 8 bytes)
pending_num_requested: 0
events attribute: Present (type: RepeatedCompositeFieldContainer)
events list length: 5
Received batch of 5 event(s)
```

### 7. Per-Event Details
```
Processing event: schema_id=... event_id=... replay_id=... payload_len=256
Decoded event keys: ['EventUuid', 'CreatedDate', 'ObjectId__c', ...]
```

---

## Testing Steps

### 1. Clean Slate Test
```bash
cd salesforce_client

# Clear old cursor
rm -f data/cursor.db

# Ensure dependencies are installed
pip install -r requirements.txt
```

### 2. Run the Function
Trigger your TimerPoller Azure Function

### 3. Analyze the Logs

Look for these specific patterns:

#### ✅ **Success Pattern**
```
✓ Connected to Salesforce Pub/Sub API
Retrieved topic info for /event/Delete_Logs__e: schema_id=...
Subscribing to /event/Delete_Logs__e from EARLIEST
Received fetch_response #1 from stream
events list length: 5
Processing event: schema_id=... event_id=...
Fetched 5 events from topic /event/Delete_Logs__e
```

#### ❌ **Empty Response Pattern**
```
✓ Connected to Salesforce Pub/Sub API
Retrieved topic info for /event/Delete_Logs__e: schema_id=...
Subscribing to /event/Delete_Logs__e from EARLIEST
Received fetch_response #1 from stream
events list length: 0
No events in this batch - empty response or keepalive. Breaking.
```
**Meaning**: Successfully connected but no events in retention window

#### ❌ **Authentication Error Pattern**
```
Connecting to Pub/Sub API at api.pubsub.salesforce.com:7443
gRPC error during subscription: StatusCode.UNAUTHENTICATED - ...
gRPC trailers: [...]
```
**Meaning**: Invalid access token or expired

#### ❌ **Topic Not Found Pattern**
```
gRPC error: StatusCode.NOT_FOUND - Topic not found
```
**Meaning**: Topic name is wrong or not enabled

#### ❌ **Schema Fetch Error Pattern**
```
Avro schema GET https://...-> 404
Schema fetch attempt failed on ...
Failed to fetch schema for ID ...
```
**Meaning**: Schema not accessible via REST API

---

## Diagnostic Questions Based on Logs

### If you see "events list length: 0"

**Question 1**: Are the test events WITHIN the retention window?
- Platform Events retention: 72 hours (3 days)
- If events were created >72h ago, they're gone

**Question 2**: What does your Salesforce dev team see?
- Ask them to check Event Monitor or Debug Logs
- Confirm events were actually published successfully

**Question 3**: Try the continuous mode with same credentials
```bash
cd ref-cliend/salesforce_client
python main.py
```
Does continuous mode receive events? If yes → batch mode issue. If no → Salesforce side issue.

---

### If you see "gRPC error: UNAUTHENTICATED"

**Check**:
1. `SF_CLIENT_ID` is correct
2. `SF_USERNAME` is correct  
3. `SF_PRIVATE_KEY_PATH` points to valid key
4. Connected App is properly configured in Salesforce
5. User has API access enabled

**Test authentication separately**:
```python
from src.app.salesforce.auth import create_jwt_assertion, get_access_token
from src.app.config.settings import get_settings

settings = get_settings()
assertion = create_jwt_assertion(
    client_id=settings.sf_client_id,
    username=settings.sf_username,
    audience=settings.sf_audience,
    private_key_path=settings.sf_private_key_path,
)
access_token, instance_url, tenant_id = get_access_token(settings.sf_login_url, assertion)
print(f"✓ Auth successful: {tenant_id}")
```

---

### If you see "Topic not found"

**Check topic name format**:
- Correct: `/event/Delete_Logs__e`
- Wrong: `Delete_Logs__e` (missing `/event/` prefix)
- Wrong: `/event/Delete_Logs` (missing `__e` suffix)

**Verify topic exists in Salesforce**:
```bash
# Use GetTopic RPC to list available topics
# Or check in Salesforce Setup > Platform Events
```

---

### If schema fetch fails

**This is interesting** - it might mean:
1. Platform event schema not accessible via REST API
2. API version mismatch (we try 64.0, 61.0, 59.0, 57.0)
3. User doesn't have permission to read event schema

**Workaround**: If REST schema fetch fails but you know continuous mode works, we could cache the schema or use a different method.

---

## Comparison Test

Run BOTH modes with same credentials and see the difference:

### Continuous Mode (Working)
```bash
cd ref-cliend/salesforce_client
# Update .env with same credentials
python main.py
# Let it run for 30 seconds, check events.db
sqlite3 events.db "SELECT COUNT(*) FROM events"
```

### Batch Mode (Not Working)
```bash
# Trigger TimerPoller
# Check logs
```

**Compare**:
- Do they use same credentials? 
- Do they connect to same org?
- Do they subscribe to same topic?

---

## Next Steps

**Please run the function and share the logs focusing on:**

1. The section between the `====` markers showing the fetch_events_via_pubsub call
2. Any error messages or warnings
3. The "events list length" line
4. Whether you see "Processing event:" logs

This will tell us exactly where it's failing:
- ❌ Connection issue?
- ❌ Authentication issue?
- ❌ Empty response issue?
- ❌ Parsing issue?

Share the logs and we'll pinpoint the exact problem! 🎯

