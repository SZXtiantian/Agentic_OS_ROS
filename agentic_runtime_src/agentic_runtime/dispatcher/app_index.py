from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


IGNORED_APP_DIRS = {"agentic_runtime_src", "app_template"}


@dataclass
class AppIndexEntry:
    app_id: str
    root: str
    config_path: str = ""
    app_yaml_path: str = ""
    description: str = ""
    runtime_type: str = "legacy"
    entrypoint: str = ""
    aios_entrypoint: str = ""
    dispatch_enabled: bool = False
    dispatch_priority: int = 0
    intents: list[str] = field(default_factory=list)
    keywords_zh: list[str] = field(default_factory=list)
    keywords_en: list[str] = field(default_factory=list)
    risk_classes: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    allowed_targets: list[str] = field(default_factory=list)
    allowed_arm_actions: list[str] = field(default_factory=list)
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AppIndex:
    def __init__(self, entries: list[AppIndexEntry]) -> None:
        self.entries = sorted(entries, key=lambda item: (-item.dispatch_priority, item.app_id))
        self._by_id = {entry.app_id: entry for entry in self.entries}

    @classmethod
    def load(cls, app_root: str | Path) -> "AppIndex":
        root = Path(app_root).expanduser()
        entries: list[AppIndexEntry] = []
        if not root.exists():
            return cls(entries)
        for app_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if app_dir.name in IGNORED_APP_DIRS:
                continue
            if "archived" in app_dir.parts or app_dir.name.startswith("archived"):
                continue
            config_path = app_dir / "config.json"
            app_yaml_path = app_dir / "app.yaml"
            if not config_path.exists() and not app_yaml_path.exists():
                continue
            entries.append(_load_entry(app_dir, config_path, app_yaml_path))
        return cls(entries)

    def get(self, app_id: str) -> AppIndexEntry | None:
        return self._by_id.get(app_id)

    def enabled_entries(self) -> list[AppIndexEntry]:
        return [entry for entry in self.entries if entry.dispatch_enabled and not entry.archived]

    def to_prompt_summary(self) -> list[dict[str, Any]]:
        return [
            {
                "app_id": entry.app_id,
                "description": entry.description,
                "intents": entry.intents,
                "keywords_zh": entry.keywords_zh,
                "keywords_en": entry.keywords_en,
                "risk_classes": entry.risk_classes,
                "allowed_targets": entry.allowed_targets,
                "allowed_arm_actions": entry.allowed_arm_actions,
            }
            for entry in self.enabled_entries()
        ]

    def to_dict(self) -> dict[str, Any]:
        return {"apps": [entry.to_dict() for entry in self.entries]}


def _load_entry(app_dir: Path, config_path: Path, app_yaml_path: Path) -> AppIndexEntry:
    config = _read_json(config_path) if config_path.exists() else {}
    app_yaml = _read_yaml(app_yaml_path) if app_yaml_path.exists() else {}
    dispatch = dict(config.get("dispatch") or {})
    return AppIndexEntry(
        app_id=str(config.get("name") or app_yaml.get("name") or app_dir.name),
        root=str(app_dir),
        config_path=str(config_path) if config_path.exists() else "",
        app_yaml_path=str(app_yaml_path) if app_yaml_path.exists() else "",
        description=str(config.get("description") or app_yaml.get("description") or ""),
        runtime_type=str(app_yaml.get("runtime_type") or "legacy"),
        entrypoint=str(app_yaml.get("entrypoint") or ""),
        aios_entrypoint=str(app_yaml.get("aios_entrypoint") or ""),
        dispatch_enabled=bool(dispatch.get("enabled", False)),
        dispatch_priority=int(dispatch.get("priority", 0)),
        intents=list(dispatch.get("intents") or []),
        keywords_zh=list(dispatch.get("keywords_zh") or []),
        keywords_en=list(dispatch.get("keywords_en") or []),
        risk_classes=list(dispatch.get("risk_classes") or []),
        required_capabilities=list(app_yaml.get("required_capabilities") or []),
        permissions=list(app_yaml.get("permissions") or []),
        allowed_targets=list(app_yaml.get("allowed_targets") or []),
        allowed_arm_actions=list(app_yaml.get("allowed_arm_actions") or []),
        archived=bool(dispatch.get("archived", False) or app_yaml.get("archived", False)),
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    return data if isinstance(data, dict) else {}
