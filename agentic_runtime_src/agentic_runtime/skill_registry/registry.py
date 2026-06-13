from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from agentic_os.kernel.capability import CapabilityRegistry
from agentic_os.kernel.skill_library import SkillRegistry as KernelSkillRegistry

from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.types import SkillManifest

from .skill_manifest import load_skill_manifest


class SkillRegistry:
    def __init__(self, skill_root: Path) -> None:
        self.skill_root = skill_root
        self.kernel = KernelSkillRegistry(skill_root)
        self.capabilities = CapabilityRegistry()
        self._skills: dict[str, SkillManifest] = {}
        self._aliases: dict[str, str] = {}

    def load(self) -> "SkillRegistry":
        if not self.skill_root.exists():
            raise SchemaInvalidError(f"skill root does not exist: {self.skill_root}")
        self.kernel.load()
        for path in sorted(self.skill_root.glob("*.yaml")):
            manifest = load_skill_manifest(path)
            self.register(manifest)
        return self

    def register(self, manifest: SkillManifest) -> None:
        self._skills[manifest.name] = manifest
        self._aliases[manifest.name.split(".")[-1]] = manifest.name
        self._aliases[manifest.name.replace(".", "_")] = manifest.name
        self.capabilities.register_skill_manifest(asdict(manifest))

    def get_skill(self, name: str) -> SkillManifest:
        key = name if name in self._skills else self._aliases.get(name)
        if not key:
            raise KeyError(f"skill not found: {name}")
        return self._skills[key]

    def list_skills(self) -> list[SkillManifest]:
        return [self._skills[name] for name in sorted(self._skills)]
