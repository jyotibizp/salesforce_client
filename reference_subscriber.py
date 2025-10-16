# subscriber.py
import io
import json
import logging
import signal
import sqlite3
import threading
from typing import Dict, List, Tuple, Optional

import certifi
import grpc
import requests
from fastavro import schemaless_reader

from pubsub_api_pb2 import FetchRequest, ReplayPreset, TopicRequest
from pubsub_api_pb2_grpc import PubSubStub

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -----------------------------
# Persistence helpers (SQLite)
# -----------------------------
def persist_event(
    decoded_event: Dict,
    schema_id: str,
    event_id: Optional[str] = None,
    replay_id_int: Optional[int] = None,
    db_path: str = "events.db",
) -> None:
    """
    Persist a decoded event to SQLite for inspection/troubleshooting.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                schema_id TEXT,
                replay_id INTEGER,
                payload_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        payload_json = json.dumps(decoded_event)
        cur.execute(
            """
            INSERT INTO events (event_id, schema_id, replay_id, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (event_id, schema_id, replay_id_int, payload_json),
        )
        conn.commit()
    finally:
        conn.close()


# -----------------------------
# Salesforce Pub/Sub helpers
# -----------------------------
def fetch_avro_schema(schema_id: str, token_response: Dict) -> Dict:
    """
    Fetch the Avro schema (COMPACT) for a platform event / CDC schema_id via REST.
    See: /services/data/vXX.X/event/eventSchema/{schemaId}?payloadFormat=COMPACT
    """
    instance_url = token_response["instance_url"]
    access_token = token_response["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Try a few recent API versions (adjust if your org supports newer)
    versions = ["64.0", "61.0", "59.0", "57.0"]
    last_err = None

    for v in versions:
        url = f"{instance_url}/services/data/v{v}/event/eventSchema/{schema_id}?payloadFormat=COMPACT"
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            logging.info("Avro schema GET %s -> %s", url, resp.status_code)
            resp.raise_for_status()
            data = resp.json()

            # Some responses wrap the actual Avro schema under "schema"; normalize both cases.
            schema = data.get("schema", data)
            if not isinstance(schema, dict):
                raise ValueError(f"Unexpected schema shape from {url}: {type(schema)}")
            return schema
        except requests.RequestException as e:
            logging.warning("Schema fetch attempt failed on %s: %s", url, e)
            last_err = e
            continue

    raise RuntimeError(f"Failed to fetch schema for ID {schema_id}: {last_err}")


def _build_metadata(token_response: Dict) -> List[Tuple[str, str]]:
    """
    Build the gRPC metadata expected by Salesforce Pub/Sub service.
    """
    access_token = token_response["access_token"]
    instance_url = token_response["instance_url"]
    # The 'id' field is like https://login.salesforce.com/id/<ORG_ID>/<USER_ID>
    tenant_id = token_response["id"].rstrip("/").split("/")[-2]
    return [
        ("accesstoken", access_token),
        ("instanceurl", instance_url),
        ("tenantid", tenant_id),
    ]


def _grpc_channel() -> grpc.Channel:
    """
    Create a secure gRPC channel to Salesforce Pub/Sub endpoint using certifi CA bundle.
    """
    with open(certifi.where(), "rb") as f:
        creds = grpc.ssl_channel_credentials(f.read())
    # You can add channel options here if needed
    return grpc.secure_channel("api.pubsub.salesforce.com:7443", creds)


def ensure_topic_exists(token_response: Dict, topic_name: str) -> bool:
    """
    Validate topic existence and that the org can subscribe to it.
    """
    metadata = _build_metadata(token_response)
    with _grpc_channel() as channel:
        stub = PubSubStub(channel)
        try:
            info = stub.GetTopic(TopicRequest(topic_name=topic_name), metadata=metadata)
            return bool(getattr(info, "can_subscribe", True))
        except grpc.RpcError as e:
            logger.error("GetTopic failed for %s: %s - %s", topic_name, e.code(), e.details())
            tr = list(e.trailing_metadata() or [])
            if tr:
                logger.error("Trailers: %s", tr)
            return False


# -----------------------------
# Signal handlers
# -----------------------------
def install_signal_handlers(stop_event: threading.Event, on_shutdown=None) -> None:
    """
    Install SIGINT/SIGTERM handlers that set the stop_event and invoke on_shutdown.
    Works on Linux/macOS. On Windows, SIGTERM may not be available; SIGINT still works.
    """
    def handler(signum, frame):
        logger.info("Signal %s received. Shutting down…", signum)
        stop_event.set()
        try:
            if on_shutdown:
                on_shutdown()
        except Exception as e:
            logger.debug("on_shutdown raised during signal handling: %s", e)

    signal.signal(signal.SIGINT, handler)
    # SIGTERM may not exist on Windows; guard it
    try:
        signal.signal(signal.SIGTERM, handler)
    except AttributeError:
        pass


# -----------------------------
# Subscriber
# -----------------------------
def subscribe_to_topic_with_token_response(
    token_response: Dict,
    topic_name: str,
    batch_size: int = 10,
    periodic_fetch_secs: int = 30,
) -> None:
    """
    Subscribe to a Salesforce Pub/Sub topic (CDC or Platform Event).
    Decodes Avro payloads and persists to SQLite.

    Args:
        token_response: dict returned by your OAuth Connect flow.
        topic_name: e.g., "/data/EventChangeEvent" or "/event/YourPlatformEvent__e".
        batch_size: number of events per fetch.
        periodic_fetch_secs: interval to continue fetching.
    """
    if not (topic_name.startswith("/event/") or topic_name.startswith("/data/")):
        logger.warning("Topic must start with /event/ or /data/. Got: %s", topic_name)

    metadata = _build_metadata(token_response)

    channel = _grpc_channel()
    stub = PubSubStub(channel)

    # Try early topic validation (optional but nice)
    if not ensure_topic_exists(token_response, topic_name):
        logger.error("Topic %s is not available or not subscribable. Check CDC/PE setup.", topic_name)
        channel.close()
        return

    logger.info("Subscribing to topic: %s", topic_name)

    stop = threading.Event()
    schema_cache: Dict[str, Dict] = {}
    stream_call_holder = {"call": None}  # hold the streaming RPC to cancel later

    def on_shutdown():
        """
        Called from signal handler and from KeyboardInterrupt path to cancel RPC and close channel.
        """
        try:
            call = stream_call_holder.get("call")
            if call is not None:
                logger.info("Cancelling streaming RPC…")
                call.cancel()
        except Exception as e:
            logger.debug("Error cancelling call: %s", e)
        try:
            logger.info("Closing gRPC channel…")
            channel.close()
        except Exception as e:
            logger.debug("Error closing channel: %s", e)

    install_signal_handlers(stop, on_shutdown=on_shutdown)

    def fetch_requests():
        # Start from latest; optionally hook in CUSTOM replay here if you store last checkpoint.
        yield FetchRequest(
            topic_name=topic_name,
            replay_preset=ReplayPreset.LATEST,
            num_requested=batch_size,
        )
        while not stop.is_set():
            # This wait is interruptible by signal handlers
            stop.wait(periodic_fetch_secs)
            if stop.is_set():
                break
            yield FetchRequest(
                topic_name=topic_name,
                num_requested=batch_size,
            )

    def _consume():
        try:
            # Keep a handle to the streaming RPC so we can cancel it on shutdown
            call = stub.Subscribe(fetch_requests(), metadata=metadata)
            stream_call_holder["call"] = call

            for fetch_resp in call:
                if stop.is_set():
                    break

                if getattr(fetch_resp, "events", None):
                    logger.info("Received batch of %d event(s).", len(fetch_resp.events))
                    for ev in fetch_resp.events:
                        nested = getattr(ev, "event", None)
                        if not nested or not nested.payload:
                            logger.warning("No ev.event.payload; skipping.")
                            continue

                        payload_bytes: bytes = nested.payload
                        schema_id: str = nested.schema_id
                        event_id: str = nested.id
                        replay_id_int = int.from_bytes(ev.replay_id, byteorder="big", signed=False)

                        logger.info(
                            "schema_id=%s event_id=%s replay_id=%s payload_len=%d",
                            schema_id, event_id, replay_id_int, len(payload_bytes)
                        )

                        # Get or fetch schema
                        schema = schema_cache.get(schema_id)
                        if schema is None:
                            try:
                                schema = fetch_avro_schema(schema_id, token_response)
                                schema_cache[schema_id] = schema
                            except Exception as e:
                                logger.error("Failed to fetch schema for %s: %s", schema_id, e)
                                continue

                        # Decode Avro payload
                        try:
                            decoded = schemaless_reader(io.BytesIO(payload_bytes), schema)

                            # CDC delete filter (optional)
                            hdr = decoded.get("ChangeEventHeader", {})
                            # change_type = hdr.get("changeType")
                            # if change_type == "DELETE":
                            #     logger.info(
                            #         "Filtered DELETE event for entity=%s ids=%s",
                            #         hdr.get("entityName"), hdr.get("recordIds")
                            #     )
                            #     continue

                            # Persist decoded record
                            persist_event(
                                decoded_event=decoded,
                                schema_id=schema_id,
                                event_id=event_id,
                                replay_id_int=replay_id_int,
                            )

                            logger.debug("Decoded keys: %s", list(decoded.keys()))
                        except Exception as decode_error:
                            logger.error("Failed to decode event %s: %s", event_id, decode_error)
                # else: heartbeat/no events; ignore
        except grpc.RpcError as e:
            if stop.is_set() and e.code() == grpc.StatusCode.CANCELLED:
                logger.info("Streaming RPC cancelled (expected on shutdown).")
            else:
                logger.error("gRPC error: %s - %s", e.code(), e.details())
                tr = list(e.trailing_metadata() or [])
                if tr:
                    logger.error("Trailers: %s", tr)
        finally:
            # Ensure RPC is cancelled if still running
            try:
                call = stream_call_holder.get("call")
                if call is not None:
                    call.cancel()
            except Exception:
                pass

    # Use non-daemon so we can cleanly join
    t = threading.Thread(target=_consume, daemon=False)
    t.start()

    try:
        logger.info("Subscriber running. Press Ctrl+C to exit.")
        # Wait until stop is signaled (by signal handler or other code)
        while not stop.is_set():
            stop.wait(1.0)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Stopping…")
        stop.set()
    finally:
        # Trigger shutdown steps
        on_shutdown()
        # Wait for the consumer to finish up (respect a timeout)
        t.join(timeout=10)
        if t.is_alive():
            logger.warning("Consumer thread did not exit within timeout; process will terminate anyway.")
