# Batch Mode Parsing - Aligned with Continuous Mode

## Changes Made

Updated batch mode (`src/app/salesforce/pubsub_client.py`) to use the **exact same parsing approach** as the working continuous mode, since continuous mode is successfully receiving events.

## What Changed

### 1. **Schema Fetching - Switched from gRPC to REST API**

**Before:**
```python
# Used gRPC GetSchema call
response = self.stub.GetSchema(request, metadata=metadata)
schema_dict = json.loads(response.schema_json)
```

**After:**
```python
# Uses REST API with multiple version fallback (same as continuous)
def fetch_avro_schema_via_rest(self, schema_id: str) -> dict:
    versions = ["64.0", "61.0", "59.0", "57.0"]
    for v in versions:
        url = f"{instance_url}/services/data/v{v}/event/eventSchema/{schema_id}?payloadFormat=COMPACT"
        resp = requests.get(url, headers=headers, timeout=30)
        return resp.json()
```

**Why:** Continuous mode uses REST API and it works. The gRPC GetSchema might have returned schema in different format.

---

### 2. **Avro Decoding - Switched from avro-python3 to fastavro**

**Before:**
```python
import avro.io
import avro.schema

bytes_reader = io.BytesIO(payload_bytes)
decoder = avro.io.BinaryDecoder(bytes_reader)
reader = avro.io.DatumReader(avro_schema)
decoded_payload = reader.read(decoder)
```

**After:**
```python
from fastavro import schemaless_reader

decoded_payload = schemaless_reader(io.BytesIO(payload_bytes), schema_dict)
```

**Why:** 
- Continuous mode uses fastavro successfully
- fastavro is faster and more reliable
- Simpler API, less room for error

---

### 3. **Event Access - Added Defensive Pattern**

**Before:**
```python
# Direct access
payload_bytes = consumer_event.event.payload
```

**After:**
```python
# Defensive with getattr (same as continuous)
nested = getattr(ev, "event", None)
if not nested or not nested.payload:
    logging.warning("No ev.event.payload; skipping event.")
    continue

payload_bytes: bytes = nested.payload
```

**Why:** Protects against malformed events and provides better error visibility.

---

### 4. **Enhanced Logging - Added Detailed Debug Info**

**Before:**
```python
logging.info("Received %d events", len(events))
```

**After:**
```python
replay_id_int = int.from_bytes(replay_id_bytes, byteorder="big", signed=False)
logging.info(
    "Processing event: schema_id=%s event_id=%s replay_id=%s payload_len=%d",
    event_schema_id, event_id, replay_id_int, len(payload_bytes)
)
logging.debug("Decoded event keys: %s", list(decoded_payload.keys()))
```

**Why:** Makes debugging much easier - you can see exactly what's being received.

---

### 5. **Better Error Handling**

**Before:**
```python
except grpc.RpcError as e:
    logging.error("gRPC error during subscription: %s", e)
    raise
```

**After:**
```python
except grpc.RpcError as e:
    logging.error("gRPC error during subscription: %s - %s", e.code(), e.details())
    # Log trailing metadata for debugging (same as continuous mode)
    tr = list(e.trailing_metadata() or [])
    if tr:
        logging.error("gRPC trailers: %s", tr)
    raise
```

**Why:** Provides more context when things go wrong, including gRPC metadata.

---

### 6. **Added fastavro Dependency**

Updated `requirements.txt`:
```
fastavro==1.9.7
```

---

## Key Changes Summary

| Aspect | Before (Not Working) | After (Aligned with Continuous) |
|--------|---------------------|--------------------------------|
| Schema Fetch | gRPC GetSchema | REST API with version fallback |
| Avro Library | avro-python3 | fastavro |
| Event Access | Direct access | Defensive getattr |
| Error Handling | Basic | Detailed with metadata |
| Logging | Minimal | Detailed per-event info |
| Replay ID Logging | Not shown | Converted to int for visibility |

---

## Testing Steps

1. **Install new dependency:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Clear cursor DB to test first run:**
   ```bash
   rm data/cursor.db
   ```

3. **Run the TimerPoller function**

4. **Check logs for:**
   ```
   Subscribing to /event/Delete_Logs__e from EARLIEST (first run)
   Retrieved schema for schema_id=... via REST
   Using schema for decoding: ...
   Received batch of X event(s) from /event/Delete_Logs__e
   Processing event: schema_id=... event_id=... replay_id=... payload_len=...
   Decoded event keys: [...]
   Fetched X events from topic /event/Delete_Logs__e
   Saved replay_id for topic /event/Delete_Logs__e
   ```

---

## What Was The Problem?

The batch mode wasn't receiving events because of parsing/decoding incompatibilities:

1. **Schema format issue**: gRPC GetSchema might have returned schema in different format than what avro-python3 expected
2. **Avro decoding**: The avro-python3 library might have had stricter requirements or different behavior
3. **Silent failures**: Direct access and minimal logging meant issues weren't visible

By aligning with the **proven working continuous mode**, we eliminate these variables.

---

## Why This Should Work Now

✅ **REST API schema fetching** - Exactly what works in continuous mode  
✅ **fastavro decoding** - Same library that successfully decodes events  
✅ **Defensive event access** - Catches malformed events  
✅ **Detailed logging** - You'll see exactly what's happening  
✅ **EARLIEST preset** - Will fetch all available events on first run  

The batch mode now uses the **identical parsing pipeline** as continuous mode, just with a different connection pattern (one-shot vs persistent).

