from __future__ import annotations

from pathlib import Path
from typing import Any


class SafeFilesystem:
    def __init__(self, storage_manager: Any) -> None:
        self.storage_manager = storage_manager

    @property
    def root(self) -> Path:
        return self.storage_manager.root

    def write(self, path: str, content: Any) -> dict[str, Any]:
        return self.storage_manager.write(path, content)

    def read(self, path: str) -> dict[str, Any]:
        return self.storage_manager.read(path)
