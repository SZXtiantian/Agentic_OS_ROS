from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.types import SkillManifest


LEGACY_REQUIRED_FIELDS = [
    "name",
    "version",
    "input_schema",
    "output_schema",
    "permission_requirements",
    "backend",
]
AGENTIC_SKILL_REQUIRED_FIELDS = [
    "schema_version",
    "name",
    "scope",
    "implementation",
    "input_schema",
    "output_schema",
]

SIMULATED_BACKEND_TYPES = {"mock", "fake", "stub", "dummy"}
AGENTIC_SKILL_BLOCK_RE = re.compile(
    r"^```json[ \t]+agentic-skill[^\n]*\n(?P<body>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def load_skill_manifest(path: Path) -> SkillManifest:
    if path.name == "SKILL.md":
        return load_skill_markdown_manifest(path)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate_skill_manifest_dict(data, source=str(path))
    data = dict(data)
    data.setdefault("scope", "system")
    data.setdefault("access", {"required": False})
    data.setdefault("implementation", dict(data.get("backend") or {}))
    data["source_path"] = str(path)
    return SkillManifest.from_dict(data)


def load_skill_markdown_manifest(path: Path) -> SkillManifest:
    markdown = path.read_text(encoding="utf-8")
    data = extract_agentic_skill_metadata(markdown, source=str(path))
    validate_skill_manifest_dict(data, source=str(path))
    data = dict(data)
    data.setdefault("version", "0.1.0")
    data.setdefault("description", _heading_description(markdown))
    data.setdefault("permission_requirements", [])
    data.setdefault("resource_requirements", {"locks": []})
    data.setdefault("safety_constraints", {})
    data.setdefault("timeout_s", int(data.get("timeout", data.get("timeout_s", 60))))
    data.setdefault("retry_policy", {"max_attempts": 0, "retry_on": []})
    data.setdefault("observability", {"audit": True})
    data.setdefault("backend", dict(data.get("implementation") or {}))
    data["source_path"] = str(path)
    data["markdown"] = markdown
    return SkillManifest.from_dict(data)


def extract_agentic_skill_metadata(markdown: str, *, source: str = "<memory>") -> dict:
    match = AGENTIC_SKILL_BLOCK_RE.search(markdown)
    if match is None:
        raise SchemaInvalidError(f"{source}: missing json agentic-skill metadata block")
    try:
        data = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        raise SchemaInvalidError(f"{source}: invalid json agentic-skill metadata: {exc}") from exc
    if not isinstance(data, dict):
        raise SchemaInvalidError(f"{source}: json agentic-skill metadata must be an object")
    return data


def validate_skill_manifest_dict(data: dict, source: str = "<memory>") -> None:
    if _is_agentic_skill_dict(data):
        _validate_agentic_skill_dict(data, source=source)
        return
    _validate_legacy_skill_dict(data, source=source)


def _validate_agentic_skill_dict(data: dict, source: str) -> None:
    for field in AGENTIC_SKILL_REQUIRED_FIELDS:
        if field not in data:
            raise SchemaInvalidError(f"{source}: missing {field}")
    if data.get("schema_version") != 1:
        raise SchemaInvalidError(f"{source}: schema_version must be 1")
    scope = str(data.get("scope") or "")
    if scope not in {"system", "app"}:
        raise SchemaInvalidError(f"{source}: scope must be system or app")
    implementation = data.get("implementation")
    if not isinstance(implementation, dict):
        raise SchemaInvalidError(f"{source}: implementation must be an object")
    implementation_type = str(implementation.get("type") or "").lower()
    if not implementation_type:
        raise SchemaInvalidError(f"{source}: implementation.type is required")
    if implementation_type in SIMULATED_BACKEND_TYPES:
        raise SchemaInvalidError(f"{source}: simulated skill implementation type '{implementation_type}' is disabled")
    if not isinstance(data.get("input_schema"), dict):
        raise SchemaInvalidError(f"{source}: input_schema must be an object")
    if not isinstance(data.get("output_schema"), dict):
        raise SchemaInvalidError(f"{source}: output_schema must be an object")
    access = data.get("access", {"required": False})
    if not isinstance(access, dict):
        raise SchemaInvalidError(f"{source}: access must be an object")
    if bool(access.get("required", False)) and not access.get("resource_type"):
        raise SchemaInvalidError(f"{source}: access.resource_type is required when access.required is true")
    if "permission_requirements" in data and not isinstance(data.get("permission_requirements"), list):
        raise SchemaInvalidError(f"{source}: permission_requirements must be a list")
    if "locks" not in data.get("resource_requirements", {"locks": []}):
        raise SchemaInvalidError(f"{source}: resource_requirements.locks is required")


def _validate_legacy_skill_dict(data: dict, source: str) -> None:
    for field in LEGACY_REQUIRED_FIELDS:
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


def _is_agentic_skill_dict(data: dict) -> bool:
    return "schema_version" in data or "implementation" in data or "scope" in data


def _heading_description(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""
