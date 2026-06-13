from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SkillManifest:
    name: str
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class SkillRegistry:
    """Kernel skill registry backed by installed skill manifests."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._skills: dict[str, SkillManifest] = {}

    def load(self) -> dict[str, SkillManifest]:
        self._skills.clear()
        if not self.root.exists():
            return self._skills
        for path in sorted(self.root.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            name = str(data.get("name") or data.get("skill") or path.stem)
            manifest = SkillManifest(
                name=name,
                description=str(data.get("description") or ""),
                permissions=list(data.get("permissions") or []),
                raw=data,
            )
            self._skills[name] = manifest
        return dict(self._skills)

    def get(self, name: str) -> SkillManifest | None:
        if not self._skills:
            self.load()
        return self._skills.get(name)

    def list(self) -> list[dict[str, Any]]:
        if not self._skills:
            self.load()
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "permissions": skill.permissions,
            }
            for skill in self._skills.values()
        ]

