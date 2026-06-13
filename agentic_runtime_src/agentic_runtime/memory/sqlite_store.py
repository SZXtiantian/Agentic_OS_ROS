from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SQLiteMemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  app_id TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  key TEXT NOT NULL,
                  value_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(app_id, key)
                )
                """
            )

    def remember(self, app_id: str, session_id: str, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory(app_id, session_id, key, value_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id, key) DO UPDATE SET
                  session_id=excluded.session_id,
                  value_json=excluded.value_json,
                  updated_at=excluded.updated_at
                """,
                (app_id, session_id, key, value_json, now, now),
            )

    def recall(self, app_id: str, key: str) -> Any:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM memory WHERE app_id = ? AND key = ?",
                (app_id, key),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])
