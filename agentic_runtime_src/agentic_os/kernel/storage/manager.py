from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentic_os.kernel.system_call import KernelSyscall


class StorageManager:
    """Safe file/artifact manager ported from AIOS storage responsibilities."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def address_request(self, syscall: KernelSyscall) -> dict[str, Any]:
        operation = syscall.operation_type
        params = syscall.params
        if operation in {"write", "write_artifact"}:
            return self.write(str(params["path"]), params.get("content", params.get("data", "")))
        if operation in {"read", "read_artifact"}:
            return self.read(str(params["path"]))
        if operation in {"list", "list_artifacts"}:
            return self.list(str(params.get("path", ".")))
        if operation in {"delete", "delete_artifact"}:
            return self.delete(str(params["path"]))
        return {"success": False, "error_code": "STORAGE_OPERATION_UNSUPPORTED", "operation": operation}

    def write(self, relative_path: str, content: Any) -> dict[str, Any]:
        path = self._safe_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            payload = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            payload = str(content)
        path.write_text(payload, encoding="utf-8")
        return {"success": True, "path": str(path), "size_bytes": path.stat().st_size}

    def read(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path)
        if not path.exists() or not path.is_file():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        return {"success": True, "path": str(path), "content": path.read_text(encoding="utf-8")}

    def list(self, relative_path: str = ".") -> dict[str, Any]:
        path = self._safe_path(relative_path)
        if not path.exists() or not path.is_dir():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        return {"success": True, "entries": sorted(child.name for child in path.iterdir())}

    def delete(self, relative_path: str) -> dict[str, Any]:
        path = self._safe_path(relative_path)
        if not path.exists() or not path.is_file():
            return {"success": False, "error_code": "STORAGE_NOT_FOUND", "path": str(path)}
        path.unlink()
        return {"success": True, "path": str(path)}

    def _safe_path(self, relative_path: str) -> Path:
        path = Path(relative_path)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"unsafe storage path: {relative_path}")
        return self.root / path

