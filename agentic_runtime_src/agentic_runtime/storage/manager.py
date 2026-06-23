from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.storage import StorageManager as KernelStorageManager

from agentic_runtime.errors import AgenticRuntimeError

from .models import ArtifactRecord


class StorageManager:
    def __init__(
        self,
        root: Path,
        *,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.root = root
        self.kernel = KernelStorageManager(root, access_manager=access_manager, event_sink=event_sink)

    def write_artifact(
        self,
        session_id: str,
        name: str,
        data: Any,
        artifact_type: str = "debug_json",
    ) -> ArtifactRecord:
        relative = self._safe_relative(name)
        kernel_result = self.kernel.write(str(Path(session_id) / relative), data)
        path = Path(str(kernel_result["path"]))
        return ArtifactRecord(
            session_id=session_id,
            name=name,
            artifact_type=artifact_type,
            path=str(path),
            size_bytes=int(kernel_result["size_bytes"]),
        )

    def _safe_relative(self, name: str) -> Path:
        path = Path(name)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise AgenticRuntimeError("STORAGE_PATH_INVALID", f"invalid artifact path: {name}")
        return path
