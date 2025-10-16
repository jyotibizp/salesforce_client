import sqlite3
import json
from typing import Dict

def persist_event(decoded_event: Dict, schema_id: str, event_id: str = None):
    """
    Save a decoded Salesforce Pub/Sub event to a local SQLite database.

    Args:
        decoded_event (Dict): The decoded Avro event payload.
        schema_id (str): The schema ID used to decode the event.
        event_id (str, optional): The event ID if available.
    """
    conn = sqlite3.connect("events.db")
    cursor = conn.cursor()

    # Create the table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            schema_id TEXT,
            payload_json TEXT
        )
    """)

    # Convert the decoded event to a JSON string
    payload_json = json.dumps(decoded_event)

    # Insert the event into the table
    cursor.execute("""
        INSERT INTO events (event_id, schema_id, payload_json)
        VALUES (?, ?, ?)
    """, (event_id, schema_id, payload_json))

    conn.commit()
    conn.close()
