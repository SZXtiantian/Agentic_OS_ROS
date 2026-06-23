from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .sqlite_store import SQLiteMemoryStore


class SQLiteKeyValueMemoryProvider:
    def __init__(self, path: Path) -> None:
        self.store = SQLiteMemoryStore(path)

    def remember(self, app_id: str, session_id: str, key: str, value: Any) -> dict[str, Any]:
        return self.store.remember(app_id, session_id, key, value)

    def recall(self, app_id: str, key: str) -> Any:
        return self.store.recall(app_id, key)

    def search(self, app_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        with self.store._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value_json, updated_at FROM memory
                WHERE app_id = ? AND (key LIKE ? OR value_json LIKE ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (app_id, f"%{query}%", f"%{query}%", int(limit)),
            ).fetchall()
        return [
            {"key": key, "value": json.loads(value_json), "updated_at": updated_at}
            for key, value_json, updated_at in rows
        ]

    def delete(self, app_id: str, key: str) -> bool:
        with self.store._connect() as conn:
            cursor = conn.execute("DELETE FROM memory WHERE app_id = ? AND key = ?", (app_id, key))
        return cursor.rowcount > 0
