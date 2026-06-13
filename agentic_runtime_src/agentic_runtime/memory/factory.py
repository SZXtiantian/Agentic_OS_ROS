from __future__ import annotations

from pathlib import Path

from .manager import MemoryManager
from .sqlite_provider import SQLiteKeyValueMemoryProvider


def create_memory_manager(provider_name: str, sqlite_path: Path) -> MemoryManager:
    if provider_name != "sqlite":
        raise ValueError(f"unsupported memory provider: {provider_name}")
    return MemoryManager(SQLiteKeyValueMemoryProvider(sqlite_path))
