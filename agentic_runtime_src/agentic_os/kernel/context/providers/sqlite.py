from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str) -> Any:
    return json.loads(value)


class SQLiteContextProvider:
    def __init__(self, db_path: str | Path, *, max_value_bytes: int = 1_000_000, max_snapshot_bytes: int = 4_000_000) -> None:
        self.db_path = Path(db_path)
        self.max_value_bytes = max_value_bytes
        self.max_snapshot_bytes = max_snapshot_bytes
        self._lock = RLock()
        self._available = True
        self._error = ""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except Exception as exc:
            self._available = False
            self._error = str(exc)

    def put(
        self,
        owner: str,
        session_id: str,
        namespace: str,
        key: str,
        value: Any,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_available()
        value_json = _json_dumps(value)
        if len(value_json.encode("utf-8")) > self.max_value_bytes:
            return {"success": False, "error_code": "CONTEXT_SNAPSHOT_TOO_LARGE", "key": key}
        now = _utc_now()
        ttl_s = metadata.get("ttl_s")
        expires_at = ""
        if ttl_s is not None:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=float(ttl_s))).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO context_kv(
                    owner_agent, session_id, namespace, key, value_json, metadata_json,
                    created_at, updated_at, expires_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_agent, session_id, namespace, key)
                DO UPDATE SET
                    value_json=excluded.value_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at
                """,
                (owner, session_id, namespace, key, value_json, _json_dumps(metadata), now, now, expires_at),
            )
        return {"success": True, "key": key, "session_id": session_id, "namespace": namespace, "updated_at": now}

    def get(self, owner: str, session_id: str, namespace: str, key: str) -> dict[str, Any] | None:
        self._require_available()
        self._purge_expired()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT value_json, metadata_json, created_at, updated_at, expires_at
                FROM context_kv
                WHERE owner_agent=? AND session_id=? AND namespace=? AND key=?
                """,
                (owner, session_id, namespace, key),
            ).fetchone()
        if row is None:
            return None
        return {
            "key": key,
            "value": _json_loads(row["value_json"]),
            "metadata": _json_loads(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"],
            "session_id": session_id,
            "namespace": namespace,
        }

    def delete(self, owner: str, session_id: str, namespace: str, key: str) -> bool:
        self._require_available()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM context_kv WHERE owner_agent=? AND session_id=? AND namespace=? AND key=?",
                (owner, session_id, namespace, key),
            )
        return cur.rowcount > 0

    def list(self, owner: str, session_id: str, namespace: str, prefix: str = "", limit: int = 100) -> list[dict[str, Any]]:
        self._require_available()
        self._purge_expired()
        like = f"{prefix}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value_json, metadata_json, created_at, updated_at, expires_at
                FROM context_kv
                WHERE owner_agent=? AND session_id=? AND namespace=? AND key LIKE ?
                ORDER BY key ASC
                LIMIT ?
                """,
                (owner, session_id, namespace, like, max(1, int(limit))),
            ).fetchall()
        return [
            {
                "key": row["key"],
                "value": _json_loads(row["value_json"]),
                "metadata": _json_loads(row["metadata_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "expires_at": row["expires_at"],
                "session_id": session_id,
                "namespace": namespace,
            }
            for row in rows
        ]

    def snapshot(
        self,
        owner: str,
        session_id: str,
        checkpoint: str,
        state: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_available()
        state_json = _json_dumps(state)
        if len(state_json.encode("utf-8")) > self.max_snapshot_bytes:
            return {"success": False, "error_code": "CONTEXT_SNAPSHOT_TOO_LARGE"}
        snapshot_id = f"ctx_{uuid4().hex}"
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO context_snapshots(
                    snapshot_id, owner_agent, session_id, checkpoint, pid,
                    syscall_id, state_json, metadata_json, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    owner,
                    session_id,
                    checkpoint,
                    str(metadata.get("pid", "")),
                    str(metadata.get("syscall_id", "")),
                    state_json,
                    _json_dumps(metadata),
                    now,
                ),
            )
        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "session_id": session_id,
            "checkpoint": checkpoint,
            "created_at": now,
            "state": state,
        }

    def recover(self, owner: str, session_id: str, checkpoint: str = "") -> dict[str, Any] | None:
        self._require_available()
        params: tuple[Any, ...]
        if checkpoint:
            where = "owner_agent=? AND session_id=? AND checkpoint=?"
            params = (owner, session_id, checkpoint)
        else:
            where = "owner_agent=? AND session_id=?"
            params = (owner, session_id)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT snapshot_id, checkpoint, state_json, metadata_json, created_at
                FROM context_snapshots
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        if row is None:
            return None
        return {
            "snapshot_id": row["snapshot_id"],
            "session_id": session_id,
            "checkpoint": row["checkpoint"],
            "state": _json_loads(row["state_json"]),
            "metadata": _json_loads(row["metadata_json"]),
            "created_at": row["created_at"],
        }

    def compact(self, owner: str, session_id: str, namespace: str, max_tokens: int) -> dict[str, Any]:
        entries = self.list(owner, session_id, namespace, limit=10_000)
        max_chars = max(1, int(max_tokens)) * 4
        payload = _json_dumps({"entries": entries})
        compacted = payload[:max_chars]
        truncated = len(payload) > len(compacted)
        return {
            "success": True,
            "session_id": session_id,
            "namespace": namespace,
            "max_tokens": max_tokens,
            "compacted": compacted,
            "truncated": truncated,
            "source_bytes": len(payload.encode("utf-8")),
        }

    def clear(self, owner: str, session_id: str, scope: str, namespace: str = "") -> int:
        self._require_available()
        with self._connect() as conn:
            if scope == "namespace":
                cur = conn.execute(
                    "DELETE FROM context_kv WHERE owner_agent=? AND session_id=? AND namespace=?",
                    (owner, session_id, namespace),
                )
            elif scope == "owner":
                cur = conn.execute("DELETE FROM context_kv WHERE owner_agent=?", (owner,))
            else:
                cur = conn.execute("DELETE FROM context_kv WHERE owner_agent=? AND session_id=?", (owner, session_id))
        return int(cur.rowcount)

    def status(self) -> dict[str, Any]:
        if not self._available:
            return {
                "state": "unavailable",
                "provider": "sqlite",
                "error_code": "CONTEXT_PROVIDER_UNAVAILABLE",
                "reason": self._error,
                "path": str(self.db_path),
            }
        try:
            with self._connect() as conn:
                kv_count = conn.execute("SELECT COUNT(*) AS count FROM context_kv").fetchone()["count"]
                snapshot_count = conn.execute("SELECT COUNT(*) AS count FROM context_snapshots").fetchone()["count"]
        except Exception as exc:
            return {
                "state": "unavailable",
                "provider": "sqlite",
                "error_code": "CONTEXT_PROVIDER_UNAVAILABLE",
                "reason": str(exc),
                "path": str(self.db_path),
            }
        return {
            "state": "ready",
            "provider": "sqlite",
            "path": str(self.db_path),
            "kv_count": int(kv_count),
            "snapshot_count": int(snapshot_count),
        }

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS context_kv (
                    owner_agent TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    namespace TEXT NOT NULL DEFAULT '',
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(owner_agent, session_id, namespace, key)
                );

                CREATE TABLE IF NOT EXISTS context_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    owner_agent TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    pid TEXT NOT NULL DEFAULT '',
                    syscall_id TEXT NOT NULL DEFAULT '',
                    state_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_context_kv_session
                    ON context_kv(owner_agent, session_id, namespace);
                CREATE INDEX IF NOT EXISTS idx_context_snapshot_session
                    ON context_snapshots(owner_agent, session_id, checkpoint, created_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _purge_expired(self) -> None:
        now = _utc_now()
        with self._connect() as conn:
            conn.execute("DELETE FROM context_kv WHERE expires_at != '' AND expires_at <= ?", (now,))

    def _require_available(self) -> None:
        if not self._available:
            raise RuntimeError(self._error or "context provider unavailable")
