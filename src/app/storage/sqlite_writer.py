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
    _ensure_dir(db_dir)
    db_path = os.path.join(db_dir, _db_name())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        rows = [
            (e["topic"], e["created_at"], json.dumps(e["record"]))
            for e in events
        ]
        if rows:
            conn.executemany(
                "INSERT INTO events(topic, created_at, payload) VALUES(?, ?, ?)", rows
            )
    return db_path, len(rows)


