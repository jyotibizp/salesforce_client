from __future__ import annotations

import os
import sqlite3
from typing import Optional


class CursorStore:
    """Stores replay IDs for Pub/Sub API subscriptions"""

    def __init__(self, db_dir: str) -> None:
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, "cursor.db")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cursors (
                    topic TEXT PRIMARY KEY,
                    replay_id BLOB
                )
                """
            )

    def get(self, topic: str) -> Optional[bytes]:
        """Get the last replay_id for a topic"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT replay_id FROM cursors WHERE topic = ?", (topic,))
            row = cur.fetchone()
            return row[0] if row else None

    def set(self, topic: str, replay_id: bytes) -> None:
        """Set the replay_id for a topic"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO cursors(topic, replay_id) VALUES(?, ?) "
                "ON CONFLICT(topic) DO UPDATE SET replay_id=excluded.replay_id",
                (topic, replay_id),
            )


