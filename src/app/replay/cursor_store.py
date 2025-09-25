from __future__ import annotations

import os
import sqlite3
from typing import Optional


class CursorStore:
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
                    last_created_at TEXT
                )
                """
            )

    def get(self, topic: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT last_created_at FROM cursors WHERE topic = ?", (topic,))
            row = cur.fetchone()
            return row[0] if row else None

    def set(self, topic: str, last_created_at: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO cursors(topic, last_created_at) VALUES(?, ?) "
                "ON CONFLICT(topic) DO UPDATE SET last_created_at=excluded.last_created_at",
                (topic, last_created_at),
            )


