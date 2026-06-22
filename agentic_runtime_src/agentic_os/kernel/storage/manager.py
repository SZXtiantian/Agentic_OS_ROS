from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall


class StorageManager:
    """Safe file/artifact manager ported from AIOS storage responsibilities."""

    FORBIDDEN_ROOT_PARTS = {
        "audit",
        "task_logs",
        "config",
        "configs",
        "bridge_profiles",
        "bridges",
        "ros2_ws",
        "ros2_bridge_src",
        "driver_config",
    }

    def __init__(
        self,
        root: str | Path,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.access_manager = access_manager
        self.event_sink = event_sink
        self.index_path = self.root / ".storage_index.sqlite3"
        self._index_available = True
        self._index_error = ""
        self._initialize_index()

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        operation = syscall.operation_type
        params = syscall.params
        try:
            if operation in {"write", "write_artifact", "sto_write"}:
                return self._kernel_response(
                    self.write(
                        str(params.get("path") or params.get("file_path")),
                        params.get("content", params.get("data", "")),
                        metadata=dict(params.get("metadata") or {}),
                    )
                )
            if operation in {"read", "read_artifact", "sto_read"}:
                return self._kernel_response(self.read(str(params.get("path") or params.get("file_path"))))
            if operation in {"list", "list_artifacts", "sto_list"}:
                return self._kernel_response(self.list(str(params.get("path", "."))))
            if operation in {"delete", "delete_artifact", "sto_delete"}:
                return self._kernel_response(self.delete(str(params["path"])))
            if operation == "sto_mount":
                return self._kernel_response(self.mount(str(params.get("collection_name") or params.get("path") or "default")))
            if operation == "sto_create_file":
                return self._kernel_response(
                    self.create_file(str(params.get("file_path") or params.get("path") or params.get("file_name")))
                )
            if operation in {"sto_create_directory", "sto_mkdir"}:
                return self._kernel_response(
                    self.create_directory(str(params.get("file_path") or params.get("path") or params.get("dir_path")))
                )
            if operation == "sto_stat":
                return self._kernel_response(self.stat(str(params.get("file_path") or params.get("path"))))
            if operation == "sto_history":
                return self._kernel_response(self.history(str(params.get("file_path") or params.get("path"))))
            if operation == "sto_index":
                return self._kernel_response(self.index(str(params.get("collection_name") or params.get("path") or "")))
            if operation == "sto_retrieve":
                return self._kernel_response(
                    self.retrieve(
                        query=str(params.get("query") or params.get("query_text") or ""),
                        collection_name=str(params.get("collection_name") or ""),
                        limit=int(params.get("limit", params.get("k", 5))),
                    )
                )
            if operation == "sto_rollback":
                return self._kernel_response(
                    self.rollback(
                        str(params.get("file_path") or params.get("path")),
                        version=str(params.get("version") or ""),
                    )
                )
            if operation == "sto_share":
                return self._kernel_response(
                    self.share(str(params.get("file_path") or params.get("path")), dict(params.get("metadata") or {}))
                )
            return KernelResponse.error("STORAGE_OPERATION_UNSUPPORTED", metadata={"operation": operation})
        except ValueError:
            raise
        except Exception as exc:
            return KernelResponse.error(
                "STORAGE_PROVIDER_UNAVAILABLE",
                metadata={"reason": str(exc), "provider_status": self.status()},
            )

    def write(self, relative_path: str, content: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        version = ""
        overwriting = path.exists()
        if overwriting:
            decision = self._check_access("overwrite", relative_path, irreversible=True)
            if not decision.get("success", True):
                return self._audit_dangerous_result("overwrite", relative_path, decision)
            version = self._save_version(path, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            payload = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            payload = str(content)
        path.write_text(payload, encoding="utf-8")
        self._index_file(relative_path, metadata=dict(metadata or {}))
        result = {"success": True, "path": str(path), "size_bytes": path.stat().st_size, "version": version}
        if overwriting:
            return self._audit_dangerous_result("overwrite", relative_path, result, version=version)
        return result

    def read(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        if not path.exists() or not path.is_file():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        return {"success": True, "path": str(path), "content": path.read_text(encoding="utf-8")}

    def list(self, relative_path: str = ".") -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=True)
        if not path.exists() or not path.is_dir():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        return {"success": True, "entries": sorted(child.name for child in path.iterdir() if not self._is_internal_path(child))}

    def delete(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        decision = self._check_access("delete", relative_path, irreversible=True)
        if not decision.get("success", True):
            return self._audit_dangerous_result("delete", relative_path, decision)
        if not path.exists() or not path.is_file():
            return self._audit_dangerous_result(
                "delete",
                relative_path,
                {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)},
            )
        path.unlink()
        self._remove_index(relative_path)
        return self._audit_dangerous_result("delete", relative_path, {"success": True, "path": str(path)})

    def mount(self, collection_name: str) -> dict[str, Any]:
        path = self._safe_path(collection_name or "default", allow_root=False)
        path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "collection_name": collection_name, "path": str(path)}

    def create_file(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=False)
        self._index_file(relative_path, metadata={})
        return {"success": True, "path": str(path), "size_bytes": 0}

    def create_directory(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(path)}

    def retrieve(self, query: str, collection_name: str = "", limit: int = 5) -> dict[str, Any]:
        root = self._safe_path(collection_name or ".", allow_root=True)
        if not root.exists() or not root.is_dir():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(root)}
        if not self._index_available:
            return {"success": False, "error_code": "STORAGE_INDEX_UNAVAILABLE", "reason": self._index_error}
        if not self._has_indexed_files(collection_name):
            indexed = self.index(collection_name)
            if not indexed.get("success", False):
                return indexed
        matches = self._search_index(query, collection_name, limit)
        return {"success": True, "matches": matches, "retrieval_mode": "lexical_fts", "semantic": False}

    def rollback(self, relative_path: str, version: str = "") -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        decision = self._check_access("rollback", relative_path, irreversible=True)
        if not decision.get("success", True):
            return self._audit_dangerous_result("rollback", relative_path, decision)
        versions = sorted(self._version_dir(relative_path).glob("*.bak"))
        if not versions:
            return self._audit_dangerous_result(
                "rollback",
                relative_path,
                {"success": False, "error_code": "STORAGE_VERSION_NOT_FOUND", "path": str(path)},
            )
        latest = self._version_dir(relative_path) / version if version else versions[-1]
        if latest not in versions:
            return self._audit_dangerous_result(
                "rollback",
                relative_path,
                {"success": False, "error_code": "STORAGE_VERSION_NOT_FOUND", "path": str(path), "version": version},
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, path)
        self._index_file(relative_path, metadata={"rollback_version": latest.name})
        return self._audit_dangerous_result(
            "rollback",
            relative_path,
            {"success": True, "path": str(path), "version": latest.name},
            version=latest.name,
        )

    def stat(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        if not path.exists():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        stat = path.stat()
        digest = ""
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "success": True,
            "path": str(path),
            "relative_path": str(Path(relative_path)),
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
            "size_bytes": int(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "sha256": digest,
        }

    def history(self, relative_path: str) -> dict[str, Any]:
        self._safe_path(relative_path, allow_root=False)
        versions = []
        for version_path in sorted(self._version_dir(relative_path).glob("*.bak")):
            stat = version_path.stat()
            versions.append(
                {
                    "version": version_path.name,
                    "path": str(version_path),
                    "size_bytes": int(stat.st_size),
                    "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(version_path.read_bytes()).hexdigest(),
                }
            )
        return {"success": True, "path": relative_path, "versions": versions}

    def index(self, collection_name: str = "") -> dict[str, Any]:
        root = self._safe_path(collection_name or ".", allow_root=True)
        if not root.exists() or not root.is_dir():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(root)}
        if not self._index_available:
            return {"success": False, "error_code": "STORAGE_INDEX_UNAVAILABLE", "reason": self._index_error}
        count = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file() or self._is_internal_path(path):
                continue
            self._index_file(str(path.relative_to(self.root)), metadata={})
            count += 1
        return {"success": True, "collection_name": collection_name, "indexed_count": count, "index_path": str(self.index_path)}

    def share(self, relative_path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        if not path.exists():
            return self._audit_dangerous_result(
                "share",
                relative_path,
                {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)},
            )
        decision = self._check_access("share", relative_path, irreversible=True)
        if not decision.get("success", True):
            return self._audit_dangerous_result("share", relative_path, decision)
        if not self._index_available:
            return self._audit_dangerous_result(
                "share",
                relative_path,
                {"success": False, "error_code": "STORAGE_SHARE_REGISTRY_UNAVAILABLE", "reason": self._index_error},
            )
        sharing_policy = {"labels": ["shared"], "metadata": dict(metadata or {})}
        self._save_share_policy(str(Path(relative_path)), sharing_policy)
        return self._audit_dangerous_result(
            "share",
            relative_path,
            {"success": True, "path": str(path), "sharing_policy": sharing_policy, "share_registry_path": str(self.index_path)},
            share_registry_path=str(self.index_path),
        )

    def share_policy(self, relative_path: str) -> dict[str, Any]:
        self._safe_path(relative_path, allow_root=False)
        if not self._index_available:
            return {"success": False, "error_code": "STORAGE_SHARE_REGISTRY_UNAVAILABLE", "reason": self._index_error}
        policy = self._load_share_policy(str(Path(relative_path)))
        if policy is None:
            return {"success": False, "error_code": "STORAGE_SHARE_NOT_FOUND", "path": relative_path}
        return {"success": True, "path": relative_path, "sharing_policy": policy, "share_registry_path": str(self.index_path)}

    def status(self) -> dict[str, Any]:
        if not self._index_available:
            index = {
                "type": "sqlite_fts5",
                "state": "unavailable",
                "error_code": "STORAGE_INDEX_UNAVAILABLE",
                "reason": self._index_error,
                "path": str(self.index_path),
            }
        else:
            try:
                with self._connect_index() as conn:
                    indexed_count = conn.execute("SELECT COUNT(*) AS count FROM storage_files").fetchone()["count"]
            except Exception as exc:
                indexed_count = 0
                index = {
                    "type": "sqlite_fts5",
                    "state": "unavailable",
                    "error_code": "STORAGE_INDEX_UNAVAILABLE",
                    "reason": str(exc),
                    "path": str(self.index_path),
                }
                share_registry = {
                    "type": "sqlite",
                    "state": "unavailable",
                    "error_code": "STORAGE_SHARE_REGISTRY_UNAVAILABLE",
                    "reason": str(exc),
                    "path": str(self.index_path),
                }
            else:
                share_count = self._share_count()
                index = {
                    "type": "sqlite_fts5",
                    "state": "ready",
                    "error_code": "",
                    "reason": "",
                    "path": str(self.index_path),
                    "indexed_count": int(indexed_count),
                }
                share_registry = {
                    "type": "sqlite",
                    "state": "ready",
                    "error_code": "",
                    "reason": "",
                    "path": str(self.index_path),
                    "share_count": int(share_count),
                }
        if not self._index_available:
            share_registry = {
                "type": "sqlite",
                "state": "unavailable",
                "error_code": "STORAGE_SHARE_REGISTRY_UNAVAILABLE",
                "reason": self._index_error,
                "path": str(self.index_path),
            }
        return {
            "state": "ready",
            "provider": "local_fs",
            "root": str(self.root),
            "index": index,
            "share_registry": share_registry,
            "semantic_retrieval": {
                "state": "unavailable",
                "error_code": "STORAGE_SEMANTIC_PROVIDER_UNCONFIGURED",
                "reason": "no real embedding/vector provider configured; retrieve uses lexical SQLite FTS",
            },
        }

    def _safe_path(self, relative_path: str, *, allow_root: bool = False) -> Path:
        path = Path(relative_path or ".")
        if path.is_absolute():
            raise ValueError(f"unsafe storage path: {relative_path}")
        if path == Path("."):
            if allow_root:
                return self.root
            raise ValueError(f"unsafe storage path: {relative_path}")
        if any(part in {"", ".."} for part in path.parts):
            raise ValueError(f"unsafe storage path: {relative_path}")
        if any(part in self.FORBIDDEN_ROOT_PARTS for part in path.parts):
            raise ValueError(f"unsafe storage path: {relative_path}")
        return self.root / path

    def _check_access(self, action: str, relative_path: str, irreversible: bool = False) -> dict[str, Any]:
        if self.access_manager is None:
            return {"success": True}
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(agent_name="storage_manager", groups=("admin",)),
                action=action,
                resource=AccessResource("storage", relative_path, owner_agent="storage_manager"),
                irreversible=irreversible,
            )
        )
        if decision.allowed:
            return {"success": True}
        return {
            "success": False,
            "error_code": decision.error_code,
            "reason": decision.reason,
            "requires_intervention": decision.requires_intervention,
        }

    def _audit_dangerous_result(
        self,
        action: str,
        relative_path: str,
        result: dict[str, Any],
        **metadata: Any,
    ) -> dict[str, Any]:
        if self.event_sink is not None:
            self.event_sink.emit(
                "storage.audit",
                action=action,
                relative_path=str(Path(relative_path)),
                success=bool(result.get("success", False)),
                error_code=str(result.get("error_code") or ""),
                irreversible=True,
                provider="local_fs",
                **metadata,
            )
        return result

    def _save_version(self, path: Path, relative_path: str) -> str:
        version_dir = self._version_dir(relative_path)
        version_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        version_name = f"{timestamp}.bak"
        shutil.copy2(path, version_dir / version_name)
        return version_name

    def _version_dir(self, relative_path: str) -> Path:
        digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        return self.root / ".storage_versions" / digest

    def _initialize_index(self) -> None:
        try:
            with self._connect_index() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS storage_files (
                        relative_path TEXT PRIMARY KEY,
                        collection_name TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        metadata_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE VIRTUAL TABLE IF NOT EXISTS storage_files_fts
                    USING fts5(relative_path UNINDEXED, collection_name UNINDEXED, content, metadata);
                    CREATE TABLE IF NOT EXISTS storage_shares (
                        relative_path TEXT PRIMARY KEY,
                        labels_json TEXT NOT NULL,
                        metadata_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
        except Exception as exc:
            self._index_available = False
            self._index_error = str(exc)

    def _connect_index(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.index_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _index_file(self, relative_path: str, metadata: dict[str, Any]) -> None:
        if not self._index_available:
            return
        path = self._safe_path(relative_path, allow_root=False)
        if not path.exists() or not path.is_file() or self._is_internal_path(path):
            return
        content = path.read_text(encoding="utf-8", errors="ignore")
        stat = path.stat()
        relative = str(path.relative_to(self.root))
        collection = Path(relative).parts[0] if Path(relative).parts else ""
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        updated_at = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        with self._connect_index() as conn:
            conn.execute(
                """
                INSERT INTO storage_files(relative_path, collection_name, content_hash, size_bytes, metadata_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    collection_name=excluded.collection_name,
                    content_hash=excluded.content_hash,
                    size_bytes=excluded.size_bytes,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (relative, collection, content_hash, int(stat.st_size), metadata_json, updated_at),
            )
            conn.execute("DELETE FROM storage_files_fts WHERE relative_path=?", (relative,))
            conn.execute(
                """
                INSERT INTO storage_files_fts(relative_path, collection_name, content, metadata)
                VALUES(?, ?, ?, ?)
                """,
                (relative, collection, content, metadata_json),
            )

    def _remove_index(self, relative_path: str) -> None:
        if not self._index_available:
            return
        relative = str(Path(relative_path))
        with self._connect_index() as conn:
            conn.execute("DELETE FROM storage_files WHERE relative_path=?", (relative,))
            conn.execute("DELETE FROM storage_files_fts WHERE relative_path=?", (relative,))

    def _has_indexed_files(self, collection_name: str = "") -> bool:
        if not self._index_available:
            return False
        if collection_name:
            sql = "SELECT COUNT(*) AS count FROM storage_files WHERE relative_path=? OR relative_path LIKE ?"
            params: tuple[Any, ...] = (collection_name, f"{collection_name.rstrip('/')}/%")
        else:
            sql = "SELECT COUNT(*) AS count FROM storage_files"
            params = ()
        with self._connect_index() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["count"]) > 0

    def _save_share_policy(self, relative_path: str, sharing_policy: dict[str, Any]) -> None:
        labels_json = json.dumps(list(sharing_policy.get("labels") or []), ensure_ascii=False, sort_keys=True)
        metadata_json = json.dumps(dict(sharing_policy.get("metadata") or {}), ensure_ascii=False, sort_keys=True)
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect_index() as conn:
            conn.execute(
                """
                INSERT INTO storage_shares(relative_path, labels_json, metadata_json, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    labels_json=excluded.labels_json,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (relative_path, labels_json, metadata_json, updated_at),
            )

    def _load_share_policy(self, relative_path: str) -> dict[str, Any] | None:
        with self._connect_index() as conn:
            row = conn.execute(
                "SELECT labels_json, metadata_json FROM storage_shares WHERE relative_path=?",
                (relative_path,),
            ).fetchone()
        if row is None:
            return None
        return {
            "labels": list(json.loads(row["labels_json"] or "[]")),
            "metadata": dict(json.loads(row["metadata_json"] or "{}")),
        }

    def _share_count(self) -> int:
        if not self._index_available:
            return 0
        with self._connect_index() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM storage_shares").fetchone()
        return int(row["count"])

    def _search_index(self, query: str, collection_name: str, limit: int) -> list[dict[str, Any]]:
        query_text = self._fts_query(query)
        collection_prefix = collection_name.rstrip("/")
        matches: list[dict[str, Any]] = []
        with self._connect_index() as conn:
            if query_text:
                rows = conn.execute(
                    """
                    SELECT f.relative_path, f.content, s.metadata_json, s.size_bytes
                    FROM storage_files_fts f
                    JOIN storage_files s ON s.relative_path = f.relative_path
                    WHERE storage_files_fts MATCH ?
                    ORDER BY bm25(storage_files_fts)
                    LIMIT ?
                    """,
                    (query_text, max(1, int(limit) * 4)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT f.relative_path, f.content, s.metadata_json, s.size_bytes
                    FROM storage_files_fts f
                    JOIN storage_files s ON s.relative_path = f.relative_path
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (max(1, int(limit) * 4),),
                ).fetchall()
        for row in rows:
            relative = str(row["relative_path"])
            if collection_prefix and relative != collection_prefix and not relative.startswith(f"{collection_prefix}/"):
                continue
            content = str(row["content"])
            path = self.root / relative
            matches.append(
                {
                    "path": str(path),
                    "relative_path": relative,
                    "content": content,
                    "snippet": content[:200],
                    "score": 1.0,
                    "metadata": {
                        "collection_name": collection_name,
                        "size_bytes": int(row["size_bytes"]),
                        **dict(json.loads(row["metadata_json"] or "{}")),
                    },
                }
            )
            if len(matches) >= limit:
                break
        return matches

    def _fts_query(self, query: str) -> str:
        tokens = [token.replace('"', "") for token in str(query).split() if token.strip()]
        return " OR ".join(f'"{token}"' for token in tokens)

    def _is_internal_path(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return True
        return any(part.startswith(".storage_") for part in relative.parts)

    def _kernel_response(self, result: dict[str, Any]) -> KernelResponse:
        if result.get("success", False):
            return KernelResponse.ok(result, data=result)
        return KernelResponse.error(str(result.get("error_code") or "STORAGE_PROVIDER_UNAVAILABLE"), metadata=result)
