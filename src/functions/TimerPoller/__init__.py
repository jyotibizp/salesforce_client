import datetime
import logging
import os
import azure.functions as func

from src.app.config.settings import get_settings
from src.app.salesforce.auth import create_jwt_assertion, get_access_token
from src.app.salesforce.events import fetch_events, topic_to_sobject_name
from src.app.replay.cursor_store import CursorStore
from src.app.storage.sqlite_writer import write_events
from src.app.storage.azure_blob import upload_file


def main(myTimer: func.TimerRequest) -> None:
    if myTimer.past_due:
        logging.info("The timer is past due!")

    utc_timestamp = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()
    logging.info("Salesforce poller function started at %s", utc_timestamp)

    settings = get_settings()

    assertion = create_jwt_assertion(
        client_id=settings.sf_client_id,
        username=settings.sf_username,
        audience=settings.sf_audience,
        private_key_path=settings.sf_private_key_path,
    )
    access_token, instance_url = get_access_token(settings.sf_login_url, assertion)

    cursor_store = CursorStore(settings.sqlite_db_dir)

    collected = []
    latest_per_topic: dict[str, str] = {}

    for topic in settings.sf_topic_names:
        sobject = topic_to_sobject_name(topic)
        since_iso = cursor_store.get(topic)
        records = fetch_events(instance_url, access_token, sobject, since_iso)
        for rec in records:
            created_at = rec["CreatedDate"]
            collected.append({
                "topic": topic,
                "created_at": created_at,
                "record": rec,
            })
            latest_per_topic[topic] = created_at

    if collected:
        db_path, count = write_events(settings.sqlite_db_dir, collected)
        blob_name = f"events/{os.path.basename(db_path)}"
        upload_file(settings.azure_storage_connection_string, settings.azure_blob_container, db_path, blob_name)
        logging.info("Uploaded %s events to blob %s", count, blob_name)
    else:
        logging.info("No new events.")

    for topic, ts in latest_per_topic.items():
        cursor_store.set(topic, ts)

    logging.info("Salesforce poller function completed at %s", datetime.datetime.utcnow().isoformat())


