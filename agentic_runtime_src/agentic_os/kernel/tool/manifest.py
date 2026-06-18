from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ToolManifest:
    name: str
    entrypoint: str
    version: str = "0"
    description: str = ""
    permissions: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    sandbox: dict[str, Any] = field(default_factory=dict)
    mcp: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolManifest":
        return cls(
            name=str(data["name"]),
            entrypoint=str(data["entrypoint"]),
            version=str(data.get("version", "0")),
            description=str(data.get("description", "")),
            permissions=tuple(data.get("permissions") or ()),
            conflicts=tuple(data.get("conflicts") or ()),
            sandbox=dict(data.get("sandbox") or {}),
            mcp=dict(data.get("mcp") or {}),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ToolManifest":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)
