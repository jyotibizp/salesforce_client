from __future__ import annotations

import logging
import grpc
import io
import json
import requests
from typing import Dict, List, Optional, Iterator
from fastavro import schemaless_reader

from src.app.salesforce.proto import pubsub_api_pb2 as pb2
from src.app.salesforce.proto import pubsub_api_pb2_grpc as pb2_grpc


PUBSUB_GRPC_ENDPOINT = "api.pubsub.salesforce.com:7443"


class PubSubClient:
    """Salesforce Pub/Sub API gRPC client for subscribing to platform events"""

    def __init__(self, access_token: str, instance_url: str, tenant_id: str):
        self.access_token = access_token
        self.instance_url = instance_url
        self.tenant_id = tenant_id
        self.channel = None
        self.stub = None

    def connect(self):
        """Establish gRPC connection to Salesforce Pub/Sub API"""
        logging.info("Connecting to Pub/Sub API at %s", PUBSUB_GRPC_ENDPOINT)
        logging.info("Using tenant_id: %s", self.tenant_id)
        logging.info("Using instance_url: %s", self.instance_url)
        logging.info("Access token length: %d chars", len(self.access_token) if self.access_token else 0)
        
        credentials = grpc.ssl_channel_credentials()
        self.channel = grpc.secure_channel(PUBSUB_GRPC_ENDPOINT, credentials)
        self.stub = pb2_grpc.PubSubStub(self.channel)
        logging.info("✓ Connected to Salesforce Pub/Sub API at %s", PUBSUB_GRPC_ENDPOINT)

    def close(self):
        """Close gRPC channel"""
        if self.channel:
            self.channel.close()
            logging.info("Closed Pub/Sub API connection")

    def _get_metadata(self) -> List[tuple]:
        """Get authentication metadata for gRPC calls"""
        return [
            ("accesstoken", self.access_token),
            ("instanceurl", self.instance_url),
            ("tenantid", self.tenant_id),
        ]

    def get_topic_info(self, topic_name: str) -> pb2.TopicInfo:
        """Get topic information including schema ID"""
        request = pb2.TopicRequest(topic_name=topic_name)
        metadata = self._get_metadata()
        response = self.stub.GetTopic(request, metadata=metadata)
        logging.info("Retrieved topic info for %s: schema_id=%s", topic_name, response.schema_id)
        return response

    def fetch_avro_schema_via_rest(self, schema_id: str) -> dict:
        """
        Fetch the Avro schema (COMPACT) for a platform event via REST API.
        Uses same approach as continuous mode for compatibility.
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Try multiple API versions (same as continuous mode)
        versions = ["64.0", "61.0", "59.0", "57.0"]
        last_err = None

        for v in versions:
            url = f"{self.instance_url}/services/data/v{v}/event/eventSchema/{schema_id}?payloadFormat=COMPACT"
            try:
                resp = requests.get(url, headers=headers, timeout=30)
                logging.info("Avro schema GET %s -> %s", url, resp.status_code)
                resp.raise_for_status()
                data = resp.json()

                # Some responses wrap the actual Avro schema under "schema"; normalize both cases
                schema = data.get("schema", data)
                if not isinstance(schema, dict):
                    raise ValueError(f"Unexpected schema shape from {url}: {type(schema)}")
                logging.info("Retrieved schema for schema_id=%s via REST", schema_id)
                return schema
            except requests.RequestException as e:
                logging.warning("Schema fetch attempt failed on %s: %s", url, e)
                last_err = e
                continue

        raise RuntimeError(f"Failed to fetch schema for ID {schema_id}: {last_err}")

    def subscribe_to_events(
        self,
        topic_name: str,
        replay_id: Optional[bytes] = None,
        num_requested: int = 100,
    ) -> Iterator[Dict]:
        """
        Subscribe to platform events from a topic

        Args:
            topic_name: Topic to subscribe to (e.g., "/event/Delete_Logs__e")
            replay_id: Optional replay ID to resume from (bytes)
            num_requested: Number of events to request per batch

        Yields:
            Dict containing decoded event payload and metadata
        """
        if not self.stub:
            raise RuntimeError("Client not connected. Call connect() first.")

        # Get topic info to retrieve schema_id
        topic_info = self.get_topic_info(topic_name)
        schema_id = topic_info.schema_id
        
        # Fetch schema via REST API (same as continuous mode)
        schema_dict = self.fetch_avro_schema_via_rest(schema_id)
        logging.info("Using schema for decoding: %s", schema_id)

        # Prepare initial fetch request
        if replay_id:
            fetch_request = pb2.FetchRequest(
                topic_name=topic_name,
                replay_preset=pb2.ReplayPreset.CUSTOM,
                replay_id=replay_id,
                num_requested=num_requested,
            )
            replay_id_int = int.from_bytes(replay_id, byteorder="big", signed=False)
            logging.info("Subscribing to %s from replay_id=%s (CUSTOM)", topic_name, replay_id_int)
        else:
            fetch_request = pb2.FetchRequest(
                topic_name=topic_name,
                replay_preset=pb2.ReplayPreset.EARLIEST,
                num_requested=num_requested,
            )
            logging.info("Subscribing to %s from EARLIEST (first run)", topic_name)

        metadata = self._get_metadata()

        # For batch mode, send single request and process response
        def request_generator():
            yield fetch_request

        try:
            logging.info("Starting Subscribe RPC call for %s...", topic_name)
            response_stream = self.stub.Subscribe(request_generator(), metadata=metadata)
            logging.info("Subscribe RPC call established, waiting for response...")

            response_count = 0
            for fetch_response in response_stream:
                response_count += 1
                logging.info("Received fetch_response #%d from stream", response_count)
                
                latest_replay_id = fetch_response.latest_replay_id
                logging.info("latest_replay_id: %s (length: %d bytes)", 
                           int.from_bytes(latest_replay_id, byteorder="big", signed=False) if latest_replay_id else None,
                           len(latest_replay_id) if latest_replay_id else 0)
                
                pending_num = getattr(fetch_response, "pending_num_requested", 0)
                logging.info("pending_num_requested: %d", pending_num)

                events_attr = getattr(fetch_response, "events", None)
                logging.info("events attribute: %s (type: %s)", 
                           "Present" if events_attr is not None else "None", 
                           type(events_attr).__name__)
                
                if events_attr is not None:
                    logging.info("events list length: %d", len(events_attr))
                
                if not events_attr:
                    logging.warning("No events in this batch - empty response or keepalive. Breaking.")
                    # No events, exit the stream
                    break

                logging.info("Received batch of %d event(s) from %s", len(fetch_response.events), topic_name)

                for ev in fetch_response.events:
                    # Defensive event access (same as continuous mode)
                    nested = getattr(ev, "event", None)
                    if not nested or not nested.payload:
                        logging.warning("No ev.event.payload; skipping event.")
                        continue

                    payload_bytes: bytes = nested.payload
                    event_schema_id: str = nested.schema_id
                    event_id: str = nested.id
                    replay_id_bytes: bytes = ev.replay_id
                    replay_id_int = int.from_bytes(replay_id_bytes, byteorder="big", signed=False)

                    logging.info(
                        "Processing event: schema_id=%s event_id=%s replay_id=%s payload_len=%d",
                        event_schema_id, event_id, replay_id_int, len(payload_bytes)
                    )

                    # Decode Avro payload using fastavro (same as continuous mode)
                    try:
                        decoded_payload = schemaless_reader(io.BytesIO(payload_bytes), schema_dict)
                        logging.debug("Decoded event keys: %s", list(decoded_payload.keys()))
                    except Exception as decode_error:
                        logging.error("Failed to decode event %s: %s", event_id, decode_error)
                        continue

                    # Yield event with metadata
                    yield {
                        "topic": topic_name,
                        "replay_id": replay_id_bytes,  # Keep as bytes for storage
                        "event_id": event_id,
                        "schema_id": event_schema_id,
                        "payload": decoded_payload,
                        "latest_replay_id": latest_replay_id,
                    }
                
                # After processing one batch, break (batch mode)
                break

        except grpc.RpcError as e:
            logging.error("gRPC error during subscription: %s - %s", e.code(), e.details())
            # Log trailing metadata for debugging (same as continuous mode)
            tr = list(e.trailing_metadata() or [])
            if tr:
                logging.error("gRPC trailers: %s", tr)
            raise


def fetch_events_via_pubsub(
    access_token: str,
    instance_url: str,
    tenant_id: str,
    topic_name: str,
    replay_id: Optional[bytes] = None,
    max_events: int = 100,
) -> List[Dict]:
    """
    Fetch events from a Salesforce topic via Pub/Sub API

    Args:
        access_token: Salesforce access token
        instance_url: Salesforce instance URL
        tenant_id: Salesforce org/tenant ID
        topic_name: Topic to subscribe to
        replay_id: Optional replay ID to resume from
        max_events: Maximum number of events to fetch

    Returns:
        List of event dictionaries
    """
    client = PubSubClient(access_token, instance_url, tenant_id)
    events = []

    try:
        client.connect()

        for event in client.subscribe_to_events(topic_name, replay_id):
            events.append(event)
            if len(events) >= max_events:
                break

        logging.info("Fetched %d events from topic %s", len(events), topic_name)

    finally:
        client.close()

    return events
