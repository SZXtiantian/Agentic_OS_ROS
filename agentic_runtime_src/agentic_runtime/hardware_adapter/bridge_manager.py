from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .installer import BridgeInstaller
from .ros2_profile import Ros2BridgeProfile


class BridgeManager:
    def __init__(self, bridge_root: Path, profile_root: Path, capability_registry=None, installer_kwargs: dict[str, Any] | None = None) -> None:
        self.bridge_root = bridge_root
        self.profile_root = profile_root
        self.capability_registry = capability_registry
        self.installer_kwargs = dict(installer_kwargs or {})
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
            "installed": metadata.get("status") == "installed_profile",
            "bridge_root": str(self.bridge_root),
            "profile_root": str(self.profile_root),
            "profiles": profiles,
            "metadata": metadata,
        }

    def plan(self, profile: Ros2BridgeProfile) -> dict:
        installer = self._installer(profile)
        return installer.plan()

    def validate(self, profile: Ros2BridgeProfile) -> dict:
        return self._installer(profile).validate()

    def build_workspace(self, profile: Ros2BridgeProfile, *, dry_run: bool = True) -> dict:
        return self._installer(profile).build_workspace(dry_run=dry_run)

    def activate(self, profile: Ros2BridgeProfile) -> dict:
        result = self._normalize_result(
            self._installer(profile).activate(),
            invalid_code="BRIDGE_LIFECYCLE_RESULT_INVALID",
            failure_code="BRIDGE_LIFECYCLE_FAILED",
        )
        self._write_lifecycle_status(profile, "active", result)
        return result

    def rollback(self, profile: Ros2BridgeProfile) -> dict:
        result = self._normalize_result(
            self._installer(profile).rollback(),
            invalid_code="BRIDGE_LIFECYCLE_RESULT_INVALID",
            failure_code="BRIDGE_LIFECYCLE_FAILED",
        )
        self._write_lifecycle_status(profile, "rolled_back", result)
        return result

    def install_profile(self, profile: Ros2BridgeProfile, *, dry_run: bool = True) -> dict:
        self.bridge_root.mkdir(parents=True, exist_ok=True)
        installer = self._installer(profile)
        install_result = self._normalize_result(
            installer.install(dry_run=dry_run),
            invalid_code="BRIDGE_INSTALL_RESULT_INVALID",
            failure_code="BRIDGE_INSTALL_FAILED",
        )
        if not install_result["success"]:
            return install_result
        plan = install_result["plan"]
        status = {
            "success": True,
            "profile": profile.name,
            "bridge_type": profile.bridge_type,
            "source_workspace": plan["source_workspace"],
            "installed_root": str(self.bridge_root),
            "capabilities": profile.capabilities or self._capability_names(),
            "packages": profile.packages or plan["required_packages"],
            "launch": profile.launch,
            "safety": profile.safety,
            "status": "installed_profile",
            "dry_run": dry_run,
            "build_timestamp": _utc_now(),
            "source_commit": plan.get("source_commit", "unknown"),
            "ros_distro": plan["ros_distro"],
            "bridge_endpoint": profile.metadata.get("bridge_endpoint", "ros2-cli://agentic-bridge"),
            "health_check_command": self._health_check_command(plan),
            "install_result": install_result,
        }
        (self.bridge_root / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self._profile_path(profile).write_text(
            yaml.safe_dump(self._profile_payload(profile, status), allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
        return status

    def _installer(self, profile: Ros2BridgeProfile) -> BridgeInstaller:
        return BridgeInstaller(
            Path(profile.source_workspace),
            self.bridge_root,
            profile_root=self.profile_root,
            required_packages=list(profile.packages or []) or None,
            **self.installer_kwargs,
        )

    def _write_lifecycle_status(self, profile: Ros2BridgeProfile, lifecycle_status: str, result: dict[str, Any]) -> None:
        status = {
            "success": result.get("success", False),
            "profile": profile.name,
            "bridge_type": profile.bridge_type,
            "source_workspace": profile.source_workspace,
            "installed_root": str(self.bridge_root),
            "status": lifecycle_status,
            "updated_at": _utc_now(),
            "result": result,
        }
        self.bridge_root.mkdir(parents=True, exist_ok=True)
        (self.bridge_root / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

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
            "packages": status.get("packages", profile.packages),
            "launch": status.get("launch", profile.launch),
            "safety": status.get("safety", profile.safety),
            "capability_specs": capabilities,
            "status": status["status"],
            "dry_run": status["dry_run"],
            "build_timestamp": status["build_timestamp"],
            "source_commit": status["source_commit"],
            "ros_distro": status["ros_distro"],
            "bridge_endpoint": status["bridge_endpoint"],
            "health_check_command": status["health_check_command"],
            "installed_root": status["installed_root"],
        }

    def _profile_path(self, profile: Ros2BridgeProfile) -> Path:
        safe_name = Path(profile.name).name
        if safe_name != profile.name or safe_name in {"", ".", ".."}:
            safe_name = "ros2_profile"
        return self.profile_root / f"{safe_name}.yaml"

    def _health_check_command(self, plan: dict[str, Any]) -> str:
        workspace_root = plan.get("workspace_root", "/home/ubuntu/agentic_ws")
        return f"source {workspace_root}/install/ros2_bridge/setup.bash && ros2 node list"

    def _normalize_result(self, result: Any, *, invalid_code: str, failure_code: str) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "success": False,
                "error_code": invalid_code,
                "reason": f"bridge operation returned {type(result).__name__}",
            }
        if "success" not in result or not isinstance(result.get("success"), bool):
            return {
                "success": False,
                "error_code": invalid_code,
                "reason": "bridge operation result missing boolean success field",
                "result": dict(result),
            }
        if result["success"]:
            return result
        if result.get("error_code"):
            return result
        normalized = dict(result)
        normalized["error_code"] = failure_code
        normalized.setdefault("reason", "bridge operation failed without error_code")
        return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
