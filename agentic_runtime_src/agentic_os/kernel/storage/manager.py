from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.system_call import KernelSyscall


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

    def __init__(self, root: str | Path, access_manager: AccessManager | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.access_manager = access_manager
        self._shares: dict[str, dict[str, Any]] = {}

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        operation = syscall.operation_type
        params = syscall.params
        if operation in {"write", "write_artifact", "sto_write"}:
            return self.write(str(params.get("path") or params.get("file_path")), params.get("content", params.get("data", "")))
        if operation in {"read", "read_artifact", "sto_read"}:
            return self.read(str(params.get("path") or params.get("file_path")))
        if operation in {"list", "list_artifacts"}:
            return self.list(str(params.get("path", ".")))
        if operation in {"delete", "delete_artifact"}:
            return self.delete(str(params["path"]))
        if operation == "sto_mount":
            return self.mount(str(params.get("collection_name") or params.get("path") or "default"))
        if operation == "sto_create_file":
            return self.create_file(str(params.get("file_path") or params.get("path") or params.get("file_name")))
        if operation == "sto_create_directory":
            return self.create_directory(str(params.get("file_path") or params.get("path") or params.get("dir_path")))
        if operation == "sto_retrieve":
            return self.retrieve(
                query=str(params.get("query") or params.get("query_text") or ""),
                collection_name=str(params.get("collection_name") or ""),
                limit=int(params.get("limit", params.get("k", 5))),
            )
        if operation == "sto_rollback":
            return self.rollback(str(params.get("file_path") or params.get("path")))
        if operation == "sto_share":
            return self.share(str(params.get("file_path") or params.get("path")), dict(params.get("metadata") or {}))
        return {"success": False, "error_code": "STORAGE_OPERATION_UNSUPPORTED", "operation": operation}

    def write(self, relative_path: str, content: Any) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        version = ""
        if path.exists():
            decision = self._check_access("overwrite", relative_path, irreversible=True)
            if not decision.get("success", True):
                return decision
            version = self._save_version(path, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            payload = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            payload = str(content)
        path.write_text(payload, encoding="utf-8")
        return {"success": True, "path": str(path), "size_bytes": path.stat().st_size, "version": version}

    def read(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        if not path.exists() or not path.is_file():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        return {"success": True, "path": str(path), "content": path.read_text(encoding="utf-8")}

    def list(self, relative_path: str = ".") -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=True)
        if not path.exists() or not path.is_dir():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        return {"success": True, "entries": sorted(child.name for child in path.iterdir())}

    def delete(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        decision = self._check_access("delete", relative_path, irreversible=True)
        if not decision.get("success", True):
            return decision
        if not path.exists() or not path.is_file():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        path.unlink()
        return {"success": True, "path": str(path)}

    def mount(self, collection_name: str) -> dict[str, Any]:
        path = self._safe_path(collection_name or "default", allow_root=False)
        path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "collection_name": collection_name, "path": str(path)}

    def create_file(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=False)
        return {"success": True, "path": str(path), "size_bytes": 0}

    def create_directory(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        path.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(path)}

    def retrieve(self, query: str, collection_name: str = "", limit: int = 5) -> dict[str, Any]:
        root = self._safe_path(collection_name or ".", allow_root=True)
        if not root.exists() or not root.is_dir():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(root)}
        query_text = query.lower()
        matches: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or ".storage_versions" in path.parts:
                continue
            relative = path.relative_to(self.root)
            content = path.read_text(encoding="utf-8", errors="ignore")
            if not query_text or query_text in content.lower() or query_text in str(relative).lower():
                matches.append(
                    {
                        "path": str(path),
                        "relative_path": str(relative),
                        "content": content,
                        "snippet": content[:200],
                        "score": 1.0 if query_text and query_text in content.lower() else 0.5,
                        "metadata": {"collection_name": collection_name},
                    }
                )
            if len(matches) >= limit:
                break
        return {"success": True, "matches": matches}

    def rollback(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        decision = self._check_access("rollback", relative_path, irreversible=True)
        if not decision.get("success", True):
            return decision
        versions = sorted(self._version_dir(relative_path).glob("*.bak"))
        if not versions:
            return {"success": False, "error_code": "STORAGE_VERSION_NOT_FOUND", "path": str(path)}
        latest = versions[-1]
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest, path)
        return {"success": True, "path": str(path), "version": latest.name}

    def share(self, relative_path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._safe_path(relative_path, allow_root=False)
        if not path.exists():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        decision = self._check_access("share", relative_path, irreversible=True)
        if not decision.get("success", True):
            return decision
        self._shares[relative_path] = {"labels": ["shared"], "metadata": dict(metadata or {})}
        return {"success": True, "path": str(path), "sharing_policy": self._shares[relative_path]}

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
