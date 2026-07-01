from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from agentic_os.kernel.capability import CapabilityRegistry
from agentic_os.kernel.skill_library import SkillRegistry as KernelSkillRegistry

from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.types import SkillManifest

from .skill_manifest import load_skill_manifest


class SkillRegistry:
    def __init__(self, skill_root: Path, app_root: Path | None = None) -> None:
        self.skill_root = Path(skill_root)
        self.skill_provider_root = self.skill_root
        self.app_root = Path(app_root) if app_root is not None else None
        self.kernel = KernelSkillRegistry(self.skill_root)
        self.capabilities = CapabilityRegistry()
        self._skills: dict[str, SkillManifest] = {}
        self._app_skills: dict[str, dict[str, SkillManifest]] = {}
        self._aliases: dict[str, str] = {}

    def load(self) -> "SkillRegistry":
        if not self.skill_root.exists():
            raise SchemaInvalidError(f"skill root does not exist: {self.skill_root}")
        self._skills.clear()
        self._aliases.clear()
        self._app_skills.clear()
        if any(self.skill_root.glob("*/SKILL.md")):
            self._load_system_skill_markdown()
        else:
            self.kernel.load()
            for path in sorted(self.skill_root.glob("*.yaml")):
                manifest = load_skill_manifest(path)
                self.register(manifest)
        return self

    def register(self, manifest: SkillManifest) -> None:
        if manifest.scope != "system":
            raise SchemaInvalidError(f"system registry cannot register non-system skill: {manifest.name}")
        self._skills[manifest.name] = manifest
        self._aliases[manifest.name.split(".")[-1]] = manifest.name
        self._aliases[manifest.name.replace(".", "_")] = manifest.name
        self.capabilities.register_skill_manifest(asdict(manifest))

    def load_app_skills(self, app_id: str, app_dir: Path | None = None) -> list[SkillManifest]:
        if not app_id:
            raise SchemaInvalidError("app_id is required to load app skills")
        root = self._resolve_app_dir(app_id, app_dir)
        skills_root = root / "skills"
        loaded: dict[str, SkillManifest] = {}
        if not skills_root.exists():
            self._app_skills[app_id] = loaded
            return []
        for path in sorted(skills_root.glob("*/SKILL.md")):
            resolved_path = path.resolve()
            if not _is_relative_to(resolved_path, root):
                raise SchemaInvalidError(f"app skill path escapes app root: {path}")
            if (path.parent / "skill.yaml").exists():
                raise SchemaInvalidError(f"app skill must use SKILL.md, not skill.yaml: {path.parent}")
            manifest = load_skill_manifest(path)
            if manifest.scope != "app":
                raise SchemaInvalidError(f"{path}: app skill scope must be app")
            if not manifest.name.startswith("app."):
                raise SchemaInvalidError(f"{path}: app skill name must start with app.")
            if manifest.name in self._skills:
                raise SchemaInvalidError(f"{path}: app skill cannot override system skill {manifest.name}")
            if manifest.name in loaded:
                raise SchemaInvalidError(f"{path}: duplicate app skill {manifest.name}")
            loaded[manifest.name] = manifest
        self._app_skills[app_id] = loaded
        return [loaded[name] for name in sorted(loaded)]

    def get_skill(self, name: str, app_id: str | None = None) -> SkillManifest:
        if app_id and name.startswith("app."):
            app_skill = self._app_skills.get(app_id, {}).get(name)
            if app_skill is not None:
                return app_skill
            raise KeyError(f"app skill not found for {app_id}: {name}")
        key = name if name in self._skills else self._aliases.get(name)
        if not key:
            raise KeyError(f"skill not found: {name}")
        return self._skills[key]

    def list_skills(self, app_id: str | None = None) -> list[SkillManifest]:
        skills = [self._skills[name] for name in sorted(self._skills)]
        if app_id:
            app_skills = self._app_skills.get(app_id, {})
            skills.extend(app_skills[name] for name in sorted(app_skills))
        return skills

    def _load_system_skill_markdown(self) -> None:
        for path in sorted(self.skill_root.glob("*/SKILL.md")):
            if path.parent.name == "interfaces":
                continue
            if (path.parent / "skill.yaml").exists():
                raise SchemaInvalidError(f"system skill must use SKILL.md, not skill.yaml: {path.parent}")
            manifest = load_skill_manifest(path)
            if manifest.scope != "system":
                raise SchemaInvalidError(f"{path}: system skill scope must be system")
            self.register(manifest)

    def _resolve_app_dir(self, app_id: str, app_dir: Path | None) -> Path:
        if app_dir is not None:
            root = Path(app_dir).expanduser().resolve()
        elif self.app_root is not None:
            root = (self.app_root / app_id).expanduser().resolve()
        else:
            raise SchemaInvalidError("app_root is required to load app skills")
        if not root.exists():
            raise SchemaInvalidError(f"app root does not exist: {root}")
        if self.app_root is not None and not _is_relative_to(root, self.app_root.expanduser().resolve()):
            raise SchemaInvalidError(f"app root escapes configured app root: {root}")
        return root


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
