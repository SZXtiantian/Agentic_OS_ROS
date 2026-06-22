from __future__ import annotations

from pathlib import Path

import yaml

from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.types import SkillManifest


REQUIRED_FIELDS = [
    "name",
    "version",
    "input_schema",
    "output_schema",
    "permission_requirements",
    "backend",
]

SIMULATED_BACKEND_TYPES = {"mock", "fake", "stub", "dummy"}


def load_skill_manifest(path: Path) -> SkillManifest:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate_skill_manifest_dict(data, source=str(path))
    return SkillManifest.from_dict(data)


def validate_skill_manifest_dict(data: dict, source: str = "<memory>") -> None:
    for field in REQUIRED_FIELDS:
        if field not in data:
            raise SchemaInvalidError(f"{source}: missing {field}")
    if not isinstance(data.get("permission_requirements"), list):
        raise SchemaInvalidError(f"{source}: permission_requirements must be a list")
    if "locks" not in data.get("resource_requirements", {"locks": []}):
        raise SchemaInvalidError(f"{source}: resource_requirements.locks is required")
    backend = data.get("backend")
    if not isinstance(backend, dict):
        raise SchemaInvalidError(f"{source}: backend must be an object")
    backend_type = str(backend.get("type") or "").lower()
    if backend_type in SIMULATED_BACKEND_TYPES:
        raise SchemaInvalidError(f"{source}: simulated skill backend type '{backend_type}' is disabled")
