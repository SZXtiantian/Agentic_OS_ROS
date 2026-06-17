from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StorageOperation:
    operation_type: str
    file_name: str = ""
    file_path: str = ""
    content: Any = None
    collection_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
