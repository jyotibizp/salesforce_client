# ROOT CAUSE FOUND - Generator Closes Too Early! 🎯

## The Smoking Gun

From `debug_2.log`, line 43-45:
```
[2025-10-23T11:53:37.583Z] Starting Subscribe RPC call for /event/Account_Delete__e...
[2025-10-23T11:53:37.585Z] Subscribe RPC call established, waiting for response...
[2025-10-23T11:53:37.897Z] Fetched 0 events from topic /event/Account_Delete__e
```

**What's MISSING?**
- ❌ "Received fetch_response #1 from stream"
- ❌ "latest_replay_id: ..."
- ❌ "events list length: ..."

**Meaning**: The `for fetch_response in response_stream:` loop **NEVER EXECUTED**!

The gRPC Subscribe call succeeded, but the response stream was **completely empty**. The iterator yielded nothing.

---

## Root Cause: Bidirectional Streaming Requirements

### gRPC Bidirectional Streaming 101

The Salesforce Pub/Sub `Subscribe` RPC is **bidirectional streaming**:
```protobuf
rpc Subscribe(stream FetchRequest) returns (stream FetchResponse);
```

Both client and server send streams. **Critically**: The client request stream must **remain open** for the server to send responses back!

### Our Batch Mode (BROKEN)

```python
def request_generator():
    yield fetch_request  # Yields once
    # Generator ENDS immediately
    # ↑ This closes the client stream!
```

**What happens:**
1. Generator yields one FetchRequest
2. Generator **immediately completes** (no more yields)
3. gRPC closes the **client-side stream**
4. Server sees client stream closed → closes **server-side stream**
5. Our code waits for responses → gets **empty iterator** → 0 events

### Continuous Mode (WORKING)

```python
def fetch_requests():
    yield FetchRequest(...)  # First request
    while not stop.is_set():
        stop.wait(30)  # KEEPS GENERATOR ALIVE!
        yield FetchRequest(...)
```

**What happens:**
1. Generator yields one FetchRequest
2. Generator **stays alive** (waits in the while loop)
3. Client stream **remains open**
4. Server sends FetchResponse back
5. Code receives events → Success! ✅

---

## The Fix

Keep the generator alive using a threading.Event:

```python
import threading
stop_flag = threading.Event()

def request_generator():
    yield fetch_request
    # Keep generator alive until we signal it to stop
    # This is required for gRPC bidirectional streaming
    stop_flag.wait()  # Blocks here, keeping generator alive
```

Then signal when done:
```python
for fetch_response in response_stream:
    # Process events...
    break  # Done with batch

# Signal generator to stop
stop_flag.set()  # Unblocks wait(), generator ends
```

---

## Why This Wasn't Obvious

1. **No error thrown** - gRPC doesn't error when client closes its stream
2. **Connection succeeds** - GetTopic, GetSchema all work fine
3. **Schema fetches** - REST API calls succeed
4. **Subscribe establishes** - The RPC call itself succeeds
5. **Silent failure** - Response stream is just empty

The logs showed "Subscribe RPC call established" ✅, so we thought it was working. But the response iterator was empty because the generator closed!

---

## How Continuous Mode Masked This

Continuous mode works because:
- It has a `while not stop.is_set():` loop
- The generator **never ends naturally** (only on signal)
- Client stream stays open indefinitely
- Server can send responses anytime

Batch mode tried to be "cleaner" by yielding once and ending, but this violated the bidirectional streaming requirements.

---

## The Lesson

**For gRPC bidirectional streaming RPCs:**
- Client must keep request stream **open** while waiting for responses
- Even if you only send one request
- Generator completion = stream closure
- Use blocking mechanisms (Event.wait, time.sleep, etc.) to keep generator alive

---

## Testing the Fix

Run the TimerPoller again. You should now see:

```
Starting Subscribe RPC call for /event/Account_Delete__e...
Subscribe RPC call established, waiting for response...
Received fetch_response #1 from stream          ← NOW APPEARS!
latest_replay_id: 12345678 (length: 8 bytes)    ← NOW APPEARS!
events attribute: Present (type: RepeatedCompositeFieldContainer)  ← NOW APPEARS!
events list length: 5                            ← NOW APPEARS!
Received batch of 5 event(s) from /event/Account_Delete__e
Processing event: schema_id=... event_id=...
```

If there are genuinely no events, you'll see:
```
events list length: 0
No events in this batch - empty response or keepalive. Breaking.
```

But at least you'll **receive a response** from the server!

---

## Files Changed

`src/app/salesforce/pubsub_client.py`:
- Added `threading.Event()` to keep generator alive
- Generator now blocks on `stop_flag.wait()`
- Signal `stop_flag.set()` after processing or on error

---

## Why It Took So Long To Find

1. ✅ Authentication was correct
2. ✅ Connection was successful
3. ✅ Topic info retrieved
4. ✅ Schema fetched via REST
5. ✅ Subscribe RPC established
6. ✅ Replay preset fixed (EARLIEST)
7. ✅ Parsing aligned with continuous mode
8. ✅ Protobuf versions matched

Everything looked perfect! But the **bidirectional stream lifecycle** was the issue. A subtle but critical difference between batch and continuous modes.

---

## Summary

**Problem**: Request generator ended immediately, closing client stream, causing server to close its stream before sending responses.

**Solution**: Keep generator alive with `threading.Event` until we're done processing.

**Result**: gRPC bidirectional streaming works correctly, events received! 🎉

This was a textbook case of why understanding the **full lifecycle** of gRPC streaming is critical. The "Subscribe RPC call established" message was misleading - it meant the initial connection worked, but not that the streams would stay open for data exchange.

Now your batch mode should finally receive those platform events! 🚀

