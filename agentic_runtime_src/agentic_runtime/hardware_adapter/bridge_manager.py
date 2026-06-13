from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .ros2_profile import Ros2BridgeProfile


class BridgeManager:
    def __init__(self, bridge_root: Path, profile_root: Path, capability_registry=None) -> None:
        self.bridge_root = bridge_root
        self.profile_root = profile_root
        self.capability_registry = capability_registry
        self.bridge_root.mkdir(parents=True, exist_ok=True)
        self.profile_root.mkdir(parents=True, exist_ok=True)

    def status(self) -> dict:
        profiles = sorted(path.stem for path in self.profile_root.glob("*.yaml"))
        metadata_path = self.bridge_root / "status.json"
        metadata = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return {
            "bridge_type": "ros2",
            "installed": self.bridge_root.exists(),
            "bridge_root": str(self.bridge_root),
            "profile_root": str(self.profile_root),
            "profiles": profiles,
            "metadata": metadata,
        }

    def install_profile(self, profile: Ros2BridgeProfile) -> dict:
        self.bridge_root.mkdir(parents=True, exist_ok=True)
        status = {
            "profile": profile.name,
            "bridge_type": profile.bridge_type,
            "source_workspace": profile.source_workspace,
            "installed_root": profile.installed_root,
            "capabilities": profile.capabilities or self._capability_names(),
            "status": "installed_mock_profile",
        }
        (self.bridge_root / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (self.profile_root / f"{profile.name}.yaml").write_text(
            yaml.safe_dump(self._profile_payload(profile, status), allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
        return status

    def _capability_names(self) -> list[str]:
        if self.capability_registry is None:
            return []
        return [spec.name for spec in self.capability_registry.list()]

    def _profile_payload(self, profile: Ros2BridgeProfile, status: dict[str, Any]) -> dict[str, Any]:
        capabilities = []
        if self.capability_registry is not None:
            capabilities = [spec.to_dict() for spec in self.capability_registry.list()]
        return {
            **profile.to_dict(),
            "capabilities": status["capabilities"],
            "capability_specs": capabilities,
            "status": status["status"],
        }
