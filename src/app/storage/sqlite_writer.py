from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Iterable, Tuple


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _db_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"events_{ts}.db"


def write_events(db_dir: str, events: Iterable[Dict]) -> Tuple[str, int]:
    """
    Write events to SQLite database

    Expected event structure:
    {
        "topic": str,
        "replay_id": bytes,
        "event_id": str,
        "payload": dict (decoded Avro payload)
    }
    """
    _ensure_dir(db_dir)
    db_path = os.path.join(db_dir, _db_name())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                replay_id BLOB NOT NULL,
                event_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        rows = [
            (e["topic"], e["replay_id"], e["event_id"], json.dumps(e["payload"]))
            for e in events
        ]
        if rows:
            conn.executemany(
                "INSERT INTO events(topic, replay_id, event_id, payload) VALUES(?, ?, ?, ?)", rows
            )
    return db_path, len(rows)


