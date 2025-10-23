# Platform Event Stream Parsing - Continuous vs Batch Mode

## Architecture Overview

### Continuous Listener (ref-cliend/subscriber.py)
- **Mode**: Long-running thread, always connected
- **Pattern**: Infinite generator keeps fetching events
- **Use case**: Real-time event processing

### Batch Poller (src/app/pubsub_client.py)
- **Mode**: Timer-triggered (30 min intervals)
- **Pattern**: Single fetch then exit
- **Use case**: Periodic polling in Azure Functions

---

## Key Differences

### 1. **Request Generator Pattern**

#### Continuous Mode
```python
def fetch_requests():
    # Initial request
    yield FetchRequest(
        topic_name=topic_name,
        replay_preset=ReplayPreset.LATEST,
        num_requested=batch_size,
    )
    # Keep yielding more requests every 30 seconds
    while not stop.is_set():
        stop.wait(periodic_fetch_secs)  # Wait 30s
        if stop.is_set():
            break
        yield FetchRequest(  # Request more events
            topic_name=topic_name,
            num_requested=batch_size,
        )
```
- **Generator keeps running**: Yields new FetchRequest every 30 seconds
- **Persistent connection**: gRPC stream stays open
- **Subsequent requests**: Don't need replay_preset (continues from last position)

#### Batch Mode
```python
def request_generator():
    yield fetch_request  # Single request only

# Then immediately breaks after first batch
for fetch_response in response_stream:
    # Process events...
    break  # Exit after ONE batch
```
- **Single request**: Generator yields once and exits
- **Connection closes**: After processing one batch
- **Each run is fresh**: New connection every 30 minutes

---

### 2. **Schema Fetching**

#### Continuous Mode - REST API
```python
# Fetches schema via Salesforce REST API
def fetch_avro_schema(schema_id: str, token_response: Dict) -> Dict:
    url = f"{instance_url}/services/data/v64.0/event/eventSchema/{schema_id}?payloadFormat=COMPACT"
    resp = requests.get(url, headers=headers, timeout=30)
    return resp.json()

# Schema cached per event
schema = schema_cache.get(schema_id)
if schema is None:
    schema = fetch_avro_schema(schema_id, token_response)
    schema_cache[schema_id] = schema  # Runtime cache
```
- **Method**: REST API call per schema_id
- **Caching**: In-memory dict, persists across batches (thread runs continuously)
- **Fallback**: Tries multiple API versions (64.0, 61.0, 59.0, 57.0)

#### Batch Mode - gRPC GetSchema
```python
# Fetches schema via gRPC Pub/Sub API
def get_schema(self, schema_id: str) -> dict:
    request = pb2.SchemaRequest(schema_id=schema_id)
    response = self.stub.GetSchema(request, metadata=metadata)
    return json.loads(response.schema_json)

# Schema fetched once per topic at start
topic_info = self.get_topic_info(topic_name)
schema_dict = self.get_schema(topic_info.schema_id)
avro_schema = avro.schema.parse(json.dumps(schema_dict))
```
- **Method**: gRPC `GetSchema` RPC call
- **Caching**: Fetched once per function run (no persistence needed)
- **Advantage**: Same gRPC connection as events

---

### 3. **Avro Decoding Libraries**

#### Continuous Mode - fastavro
```python
from fastavro import schemaless_reader

decoded = schemaless_reader(io.BytesIO(payload_bytes), schema)
```
- **Library**: `fastavro` (faster, C-based)
- **Method**: Schemaless reader

#### Batch Mode - avro-python3
```python
import avro.io
import avro.schema

bytes_reader = io.BytesIO(payload_bytes)
decoder = avro.io.BinaryDecoder(bytes_reader)
reader = avro.io.DatumReader(avro_schema)
decoded_payload = reader.read(decoder)
```
- **Library**: `avro-python3` (standard library)
- **Method**: BinaryDecoder + DatumReader pattern
- **Verbose but explicit**

---

### 4. **Replay ID Handling**

#### Continuous Mode
```python
replay_id_int = int.from_bytes(ev.replay_id, byteorder="big", signed=False)
# Stores as integer for debugging
persist_event(replay_id_int=replay_id_int, ...)
```
- **Storage**: Converts bytes → int for logging/debugging
- **Display**: Easier to read in logs (e.g., `12345678`)

#### Batch Mode
```python
# Keeps as bytes
yield {
    "replay_id": consumer_event.replay_id,  # bytes type
    ...
}

# Saved directly as bytes to SQLite
cursor_store.set(topic, replay_id)  # BLOB type
```
- **Storage**: Keeps raw bytes
- **Advantage**: No conversion overhead, matches protobuf type

---

### 5. **Event Structure & Access**

#### Continuous Mode
```python
for ev in fetch_resp.events:
    nested = getattr(ev, "event", None)  # Defensive access
    if not nested or not nested.payload:
        logger.warning("No ev.event.payload; skipping.")
        continue
    
    payload_bytes: bytes = nested.payload
    schema_id: str = nested.schema_id
    event_id: str = nested.id
    replay_id_int = int.from_bytes(ev.replay_id, ...)
```
- **Defensive**: Uses `getattr()` to avoid AttributeError
- **Safety checks**: Validates payload exists

#### Batch Mode
```python
for consumer_event in fetch_response.events:
    payload_bytes = consumer_event.event.payload
    # Direct access (assumes structure is valid)
    
    yield {
        "topic": topic_name,
        "replay_id": consumer_event.replay_id,
        "event_id": consumer_event.event.id,
        "schema_id": consumer_event.event.schema_id,
        "payload": decoded_payload,
    }
```
- **Direct access**: Assumes protobuf structure is always valid
- **Returns dict**: Clean dict output for downstream processing

---

### 6. **Error Handling**

#### Continuous Mode
```python
except grpc.RpcError as e:
    if stop.is_set() and e.code() == grpc.StatusCode.CANCELLED:
        logger.info("Streaming RPC cancelled (expected on shutdown).")
    else:
        logger.error("gRPC error: %s - %s", e.code(), e.details())
        tr = list(e.trailing_metadata() or [])  # Debug metadata
        if tr:
            logger.error("Trailers: %s", tr)
```
- **Detailed**: Logs trailing metadata for debugging
- **Graceful shutdown**: Differentiates expected vs unexpected cancellations

#### Batch Mode
```python
except grpc.RpcError as e:
    logging.error("gRPC error during subscription: %s", e)
    raise  # Re-raise for caller to handle
```
- **Simple**: Logs and re-raises
- **Function-level**: Azure Functions handles retries

---

### 7. **Connection Management**

#### Continuous Mode
```python
channel = _grpc_channel()
stub = PubSubStub(channel)

# Runs in thread
t = threading.Thread(target=_consume, daemon=False)
t.start()

# Signal handler cancels on shutdown
def on_shutdown():
    call.cancel()
    channel.close()
```
- **Long-lived**: Connection persists for hours/days
- **Signal handling**: SIGINT/SIGTERM for graceful shutdown
- **Thread-based**: Non-blocking main thread

#### Batch Mode
```python
client = PubSubClient(access_token, instance_url, tenant_id)
try:
    client.connect()
    for event in client.subscribe_to_events(...):
        events.append(event)
finally:
    client.close()  # Always closes connection
```
- **Short-lived**: Connect → fetch → disconnect
- **Context manager pattern**: Clean resource cleanup
- **Synchronous**: Blocks until done

---

## Parsing Logic Comparison Table

| Aspect | Continuous Mode | Batch Mode |
|--------|----------------|------------|
| **Connection** | Persistent gRPC stream | One-shot per run |
| **Request Generator** | Infinite (yields every 30s) | Single yield |
| **Schema Fetch** | REST API + runtime cache | gRPC GetSchema per run |
| **Avro Library** | fastavro (faster) | avro-python3 (standard) |
| **Replay ID** | Converted to int | Kept as bytes |
| **Event Access** | Defensive (getattr) | Direct access |
| **Error Handling** | Detailed logging | Simple re-raise |
| **Threading** | Separate thread | Synchronous |
| **Lifecycle** | Hours/days | Minutes |

---

## Which Approach is Better?

### Continuous Mode ✅
- **Real-time processing** with minimal latency
- **Lower overhead** (persistent connection)
- **Complex** (threading, signals, graceful shutdown)

### Batch Mode ✅
- **Simpler** code and debugging
- **Better for Azure Functions** (stateless, timer-triggered)
- **More robust** (fresh connection each run)
- **Cost-effective** for periodic polling

---

## Recommendations

### Both implementations are parsing correctly!
The core parsing logic is sound in both:
1. ✅ gRPC Subscribe call
2. ✅ Avro payload decoding
3. ✅ Replay ID tracking
4. ✅ Event structure extraction

### The fix you needed was unrelated to parsing:
The issue was using `LATEST` instead of `EARLIEST` on first run - this was a **replay preset** problem, not a parsing problem.

### Consider alignment:
If you want consistency, you could:
- Standardize on `fastavro` for both (faster)
- Use same error handling patterns
- Store replay_id consistently (bytes or int, not mixed)

But honestly, both are working fine for their respective use cases! 🎯

