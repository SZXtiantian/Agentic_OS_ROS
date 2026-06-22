from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..note import MemoryNote, utc_now
from .in_memory import can_read


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str) -> Any:
    return json.loads(value)


class SQLiteMemoryProvider:
    """Persistent MemoryProvider backed by SQLite and FTS5."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._available = True
        self._error = ""
        self._fts_available = True
        self._fts_error = ""
        self._last_error: dict[str, str] = {"operation": "", "error_code": "", "reason": ""}
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except Exception as exc:
            self._available = False
            self._error = str(exc)
            self._record_error("initialize", "MEMORY_PROVIDER_UNAVAILABLE", str(exc))

    def add_memory(self, note: MemoryNote) -> dict[str, Any]:
        self._require_available()
        now = utc_now()
        note.created_at = note.created_at or now
        note.updated_at = now
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_notes(
                    id, owner_agent, user_id, content_json, content_text, context,
                    keywords_json, tags_json, category, timestamp, metadata_json,
                    sharing_policy, memory_type, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    owner_agent=excluded.owner_agent,
                    user_id=excluded.user_id,
                    content_json=excluded.content_json,
                    content_text=excluded.content_text,
                    context=excluded.context,
                    keywords_json=excluded.keywords_json,
                    tags_json=excluded.tags_json,
                    category=excluded.category,
                    timestamp=excluded.timestamp,
                    metadata_json=excluded.metadata_json,
                    sharing_policy=excluded.sharing_policy,
                    memory_type=excluded.memory_type,
                    updated_at=excluded.updated_at
                """,
                self._note_params(note),
            )
            self._upsert_fts(conn, note)
        return {"success": True, "memory_id": note.id}

    def remove_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        self._require_available()
        current = self.get_memory(memory_id, agent_name)
        if not current.get("success", False):
            return current
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memory_notes WHERE id=?", (memory_id,))
            if self._fts_available:
                conn.execute("DELETE FROM memory_notes_fts WHERE id=?", (memory_id,))
        deleted = cur.rowcount > 0
        return {"success": deleted, "memory_id": memory_id, "error_code": "" if deleted else "MEMORY_NOT_FOUND"}

    def update_memory(self, note: MemoryNote) -> dict[str, Any]:
        self._require_available()
        original = self.get_memory(note.id, note.owner_agent)
        if not original.get("success", False):
            return original
        original_note = self._note_from_dict(original["memory"])
        if original_note.owner_agent != note.owner_agent:
            return {"success": False, "memory_id": note.id, "error_code": "MEMORY_FORBIDDEN"}
        note.created_at = original_note.created_at
        note.updated_at = utc_now()
        return self.add_memory(note)

    def get_memory(self, memory_id: str, agent_name: str = "") -> dict[str, Any]:
        self._require_available()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memory_notes WHERE id=?", (memory_id,)).fetchone()
        if row is None:
            return {"success": False, "error_code": "MEMORY_NOT_FOUND"}
        note = self._note_from_row(row)
        if agent_name and not can_read(note, agent_name):
            return {"success": False, "error_code": "MEMORY_FORBIDDEN"}
        return {"success": True, "memory": note.to_dict()}

    def retrieve_memory(self, query: str, agent_name: str, limit: int = 5, user_id: str = "") -> dict[str, Any]:
        self._require_available()
        if not self._fts_available:
            return {
                "success": False,
                "error_code": "MEMORY_INDEX_UNAVAILABLE",
                "reason": self._fts_error,
            }
        query_text = self._fts_query(query)
        with self._connect() as conn:
            if query_text:
                rows = conn.execute(
                    """
                    SELECT n.*
                    FROM memory_notes_fts f
                    JOIN memory_notes n ON n.id = f.id
                    WHERE memory_notes_fts MATCH ?
                    ORDER BY bm25(memory_notes_fts)
                    LIMIT ?
                    """,
                    (query_text, max(1, int(limit) * 4)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_notes ORDER BY updated_at DESC LIMIT ?",
                    (max(1, int(limit) * 4),),
                ).fetchall()
        readable: list[MemoryNote] = []
        for row in rows:
            note = self._note_from_row(row)
            if can_read(note, agent_name, user_id):
                readable.append(note)
            if len(readable) >= limit:
                break
        return {"success": True, "memories": [note.to_dict() for note in readable]}

    def list_notes(self, agent_name: str = "", limit: int = 100) -> list[MemoryNote]:
        self._require_available()
        if agent_name:
            sql = "SELECT * FROM memory_notes WHERE owner_agent=? ORDER BY created_at ASC LIMIT ?"
            params: tuple[Any, ...] = (agent_name, int(limit))
        else:
            sql = "SELECT * FROM memory_notes ORDER BY created_at ASC LIMIT ?"
            params = (int(limit),)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._note_from_row(row) for row in rows]

    def export_memories(self, agent_name: str, path: str | Path) -> dict[str, Any]:
        destination = Path(path)
        try:
            self._require_available()
            destination.parent.mkdir(parents=True, exist_ok=True)
            notes = [note.to_dict() for note in self.list_notes(agent_name, limit=100_000)]
            with destination.open("w", encoding="utf-8") as handle:
                for note in notes:
                    handle.write(_json_dumps(note) + "\n")
        except Exception as exc:
            error_code = "MEMORY_PROVIDER_UNAVAILABLE" if not self._available else "MEMORY_EXPORT_FAILED"
            return self._failure(
                "export",
                error_code,
                str(exc),
                path=str(destination),
            )
        return {"success": True, "path": str(destination), "count": len(notes)}

    def import_memories(self, agent_name: str, path: str | Path) -> dict[str, Any]:
        source = Path(path)
        try:
            self._require_available()
            if not source.exists():
                return self._failure(
                    "import",
                    "MEMORY_IMPORT_NOT_FOUND",
                    f"memory import file not found: {source}",
                    path=str(source),
                )
            count = 0
            with source.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = _json_loads(line)
                    except json.JSONDecodeError as exc:
                        return self._failure(
                            "import",
                            "MEMORY_IMPORT_INVALID_JSON",
                            f"{exc.msg} at line {line_number}",
                            path=str(source),
                            line_number=line_number,
                        )
                    if not isinstance(payload, dict):
                        return self._failure(
                            "import",
                            "MEMORY_IMPORT_INVALID_RECORD",
                            f"memory import record at line {line_number} must be a JSON object",
                            path=str(source),
                            line_number=line_number,
                        )
                    note = self._note_from_dict(payload)
                    if note.owner_agent and note.owner_agent != agent_name:
                        return self._failure(
                            "import",
                            "MEMORY_ACCESS_DENIED",
                            f"memory {note.id} is owned by {note.owner_agent}",
                            path=str(source),
                            memory_id=note.id,
                        )
                    note.owner_agent = agent_name
                    result = self.add_memory(note)
                    if not result.get("success", False):
                        self._record_error("import", str(result.get("error_code") or "MEMORY_IMPORT_FAILED"), str(result))
                        return result
                    count += 1
        except Exception as exc:
            error_code = "MEMORY_PROVIDER_UNAVAILABLE" if not self._available else "MEMORY_IMPORT_FAILED"
            return self._failure(
                "import",
                error_code,
                str(exc),
                path=str(source),
            )
        return {"success": True, "path": str(source), "count": count}

    def status(self) -> dict[str, Any]:
        if not self._available:
            return {
                "state": "unavailable",
                "provider": "sqlite",
                "error_code": "MEMORY_PROVIDER_UNAVAILABLE",
                "reason": self._error,
                "path": str(self.db_path),
                "db_path": str(self.db_path),
                "fts_available": bool(self._fts_available),
                "last_error": dict(self._last_error),
            }
        try:
            with self._connect() as conn:
                count = conn.execute("SELECT COUNT(*) AS count FROM memory_notes").fetchone()["count"]
        except Exception as exc:
            self._record_error("status", "MEMORY_PROVIDER_UNAVAILABLE", str(exc))
            return {
                "state": "unavailable",
                "provider": "sqlite",
                "error_code": "MEMORY_PROVIDER_UNAVAILABLE",
                "reason": str(exc),
                "path": str(self.db_path),
                "db_path": str(self.db_path),
                "fts_available": bool(self._fts_available),
                "last_error": dict(self._last_error),
            }
        index_state = "ready" if self._fts_available else "unavailable"
        return {
            "state": "ready",
            "provider": "sqlite",
            "path": str(self.db_path),
            "db_path": str(self.db_path),
            "note_count": int(count),
            "fts_available": bool(self._fts_available),
            "last_error": dict(self._last_error),
            "index": {
                "type": "sqlite_fts5",
                "state": index_state,
                "error_code": "" if self._fts_available else "MEMORY_INDEX_UNAVAILABLE",
                "reason": self._fts_error,
            },
        }

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_notes (
                    id TEXT PRIMARY KEY,
                    owner_agent TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT '',
                    content_json TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    context TEXT NOT NULL DEFAULT '',
                    keywords_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    sharing_policy TEXT NOT NULL DEFAULT 'private',
                    memory_type TEXT NOT NULL DEFAULT 'episodic',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_owner ON memory_notes(owner_agent, updated_at);
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_notes_fts
                    USING fts5(id UNINDEXED, owner_agent UNINDEXED, content, context, keywords, tags)
                    """
                )
            except sqlite3.Error as exc:
                self._fts_available = False
                self._fts_error = str(exc)
                self._record_error("initialize_fts", "MEMORY_INDEX_UNAVAILABLE", str(exc))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _require_available(self) -> None:
        if not self._available:
            raise RuntimeError(self._error or "memory provider unavailable")

    def _record_error(self, operation: str, error_code: str, reason: str) -> None:
        self._last_error = {
            "operation": str(operation),
            "error_code": str(error_code),
            "reason": str(reason),
        }

    def _failure(self, operation: str, error_code: str, reason: str, **metadata: Any) -> dict[str, Any]:
        self._record_error(operation, error_code, reason)
        return {"success": False, "error_code": error_code, "reason": reason, **metadata}

    def _upsert_fts(self, conn: sqlite3.Connection, note: MemoryNote) -> None:
        if not self._fts_available:
            return
        conn.execute("DELETE FROM memory_notes_fts WHERE id=?", (note.id,))
        conn.execute(
            """
            INSERT INTO memory_notes_fts(id, owner_agent, content, context, keywords, tags)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                note.id,
                note.owner_agent,
                self._content_text(note.content),
                note.context,
                " ".join(note.keywords),
                " ".join(note.tags),
            ),
        )

    def _note_params(self, note: MemoryNote) -> tuple[Any, ...]:
        return (
            note.id,
            note.owner_agent,
            note.user_id,
            _json_dumps(note.content),
            self._content_text(note.content),
            note.context,
            _json_dumps(note.keywords),
            _json_dumps(note.tags),
            note.category,
            note.timestamp or datetime.now(timezone.utc).isoformat(),
            _json_dumps(note.metadata),
            note.sharing_policy,
            note.memory_type,
            note.created_at,
            note.updated_at,
        )

    def _note_from_row(self, row: sqlite3.Row) -> MemoryNote:
        return MemoryNote(
            id=row["id"],
            content=_json_loads(row["content_json"]),
            owner_agent=row["owner_agent"],
            user_id=row["user_id"],
            context=row["context"],
            keywords=list(_json_loads(row["keywords_json"])),
            tags=list(_json_loads(row["tags_json"])),
            category=row["category"],
            timestamp=row["timestamp"],
            metadata=dict(_json_loads(row["metadata_json"])),
            sharing_policy=row["sharing_policy"],
            memory_type=row["memory_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _note_from_dict(self, payload: dict[str, Any]) -> MemoryNote:
        return MemoryNote(
            id=str(payload.get("id") or ""),
            content=payload.get("content", ""),
            owner_agent=str(payload.get("owner_agent") or ""),
            user_id=str(payload.get("user_id") or ""),
            context=str(payload.get("context") or ""),
            keywords=list(payload.get("keywords") or []),
            tags=list(payload.get("tags") or []),
            category=str(payload.get("category") or ""),
            timestamp=str(payload.get("timestamp") or utc_now()),
            metadata=dict(payload.get("metadata") or {}),
            sharing_policy=str(payload.get("sharing_policy") or "private"),
            memory_type=str(payload.get("memory_type") or "episodic"),
            created_at=str(payload.get("created_at") or utc_now()),
            updated_at=str(payload.get("updated_at") or utc_now()),
        )

    def _fts_query(self, query: str) -> str:
        tokens = [token.replace('"', "") for token in str(query).split() if token.strip()]
        return " OR ".join(f'"{token}"' for token in tokens)

    def _content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        return _json_dumps(content)
