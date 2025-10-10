import datetime
import logging
import os
import azure.functions as func

from src.app.config.settings import get_settings
from src.app.salesforce.auth import create_jwt_assertion, get_access_token
from src.app.salesforce.pubsub_client import fetch_events_via_pubsub
from src.app.replay.cursor_store import CursorStore
from src.app.storage.sqlite_writer import write_events
from src.app.storage.azure_blob import upload_file


def main(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")

    utc_timestamp = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
    logging.info("Salesforce Pub/Sub poller function started at %s", utc_timestamp)

    settings = get_settings()

    # Authenticate to Salesforce
    assertion = create_jwt_assertion(
        client_id=settings.sf_client_id,
        username=settings.sf_username,
        audience=settings.sf_audience,
        private_key_path=settings.sf_private_key_path,
    )
    access_token, instance_url, tenant_id = get_access_token(settings.sf_login_url, assertion)
    logging.info("Authenticated to Salesforce - Org ID: %s", tenant_id)

    cursor_store = CursorStore(settings.sqlite_db_dir)

    collected = []
    latest_per_topic: dict[str, bytes] = {}

    # Subscribe to each topic via Pub/Sub API
    for topic in settings.sf_topic_names:
        replay_id = cursor_store.get(topic)

        if replay_id:
            logging.info("Resuming subscription to %s from saved replay_id", topic)
        else:
            logging.info("Starting new subscription to %s from LATEST", topic)

        try:
            # Fetch events via Pub/Sub API
            events = fetch_events_via_pubsub(
                access_token=access_token,
                instance_url=instance_url,
                tenant_id=tenant_id,
                topic_name=topic,
                replay_id=replay_id,
                max_events=100,
            )

            for event in events:
                collected.append(event)
                # Track latest replay_id for this topic
                latest_per_topic[topic] = event["replay_id"]

            logging.info("Fetched %d events from topic %s", len(events), topic)

        except Exception as e:
            logging.error("Error fetching events from topic %s: %s", topic, e)
            continue

    if collected:
        db_path, count = write_events(settings.sqlite_db_dir, collected)
        logging.info("Saved %s events to %s", count, db_path)

        # Only upload to Azure Blob Storage if not in local environment
        environment = os.getenv("ENVIRONMENT", "").lower()
        if environment != "local":
            blob_name = f"events/{os.path.basename(db_path)}"
            upload_file(settings.azure_storage_connection_string, settings.azure_blob_container, db_path, blob_name)
            logging.info("Uploaded %s events to blob %s", count, blob_name)
    else:
        logging.info("No new events.")

    # Update cursors with latest replay IDs
    for topic, replay_id in latest_per_topic.items():
        cursor_store.set(topic, replay_id)
        logging.info("Updated replay_id for topic %s", topic)

    logging.info("Salesforce Pub/Sub poller function completed at %s", datetime.datetime.utcnow().isoformat())


