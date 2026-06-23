from __future__ import annotations

from pathlib import Path

from agentic_os.kernel.access import AccessManager
from agentic_os.kernel.hooks import KernelEventSink

from .manager import MemoryManager
from .sqlite_provider import SQLiteKeyValueMemoryProvider


def create_memory_manager(
    provider_name: str,
    sqlite_path: Path,
    *,
    access_manager: AccessManager | None = None,
    event_sink: KernelEventSink | None = None,
) -> MemoryManager:
    if provider_name != "sqlite":
        raise ValueError(f"unsupported memory provider: {provider_name}")
    return MemoryManager(SQLiteKeyValueMemoryProvider(sqlite_path), access_manager=access_manager, event_sink=event_sink)
