from __future__ import annotations

import logging
import grpc
import avro.io
import avro.schema
import io
import json
from typing import Dict, List, Optional, Iterator

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
        credentials = grpc.ssl_channel_credentials()
        self.channel = grpc.secure_channel(PUBSUB_GRPC_ENDPOINT, credentials)
        self.stub = pb2_grpc.PubSubStub(self.channel)
        logging.info("Connected to Salesforce Pub/Sub API at %s", PUBSUB_GRPC_ENDPOINT)

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

    def get_schema(self, schema_id: str) -> dict:
        """Get Avro schema for a given schema ID"""
        request = pb2.SchemaRequest(schema_id=schema_id)
        metadata = self._get_metadata()
        response = self.stub.GetSchema(request, metadata=metadata)
        schema_dict = json.loads(response.schema_json)
        logging.info("Retrieved schema for schema_id=%s", schema_id)
        return schema_dict

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

        # Get topic info and schema
        topic_info = self.get_topic_info(topic_name)
        schema_dict = self.get_schema(topic_info.schema_id)
        avro_schema = avro.schema.parse(json.dumps(schema_dict))

        # Prepare initial fetch request
        if replay_id:
            fetch_request = pb2.FetchRequest(
                topic_name=topic_name,
                replay_preset=pb2.ReplayPreset.CUSTOM,
                replay_id=replay_id,
                num_requested=num_requested,
            )
            logging.info("Subscribing to %s from replay_id (CUSTOM)", topic_name)
        else:
            fetch_request = pb2.FetchRequest(
                topic_name=topic_name,
                replay_preset=pb2.ReplayPreset.LATEST,
                num_requested=num_requested,
            )
            logging.info("Subscribing to %s from LATEST", topic_name)

        metadata = self._get_metadata()

        # For batch mode, send single request and process response
        def request_generator():
            yield fetch_request

        try:
            response_stream = self.stub.Subscribe(request_generator(), metadata=metadata)

            for fetch_response in response_stream:
                latest_replay_id = fetch_response.latest_replay_id

                if not fetch_response.events:
                    logging.info("Received keepalive with latest_replay_id")
                    # No events, exit the stream
                    break

                logging.info("Received %d events", len(fetch_response.events))

                for consumer_event in fetch_response.events:
                    # Decode Avro payload
                    payload_bytes = consumer_event.event.payload
                    bytes_reader = io.BytesIO(payload_bytes)
                    decoder = avro.io.BinaryDecoder(bytes_reader)
                    reader = avro.io.DatumReader(avro_schema)
                    decoded_payload = reader.read(decoder)

                    # Yield event with metadata
                    yield {
                        "topic": topic_name,
                        "replay_id": consumer_event.replay_id,
                        "event_id": consumer_event.event.id,
                        "schema_id": consumer_event.event.schema_id,
                        "payload": decoded_payload,
                        "latest_replay_id": latest_replay_id,
                    }
                
                # After processing one batch, break (batch mode)
                break

        except grpc.RpcError as e:
            logging.error("gRPC error during subscription: %s", e)
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
