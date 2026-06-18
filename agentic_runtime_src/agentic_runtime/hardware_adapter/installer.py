from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BRIDGE_PACKAGES = [
    "agentic_msgs",
    "agentic_world_model",
    "agentic_safety_guard",
    "agentic_capability_bridge",
    "agentic_app_runtime_bridge",
]

CommandRunner = Callable[[list[str], int], subprocess.CompletedProcess[str]]


class BridgeInstaller:
    def __init__(
        self,
        source_workspace: Path,
        install_root: Path,
        *,
        profile_root: Path | None = None,
        ros_distro: str = "humble",
        required_packages: list[str] | None = None,
        ros_setup_path: Path | None = None,
        command_runner: CommandRunner | None = None,
        timeout_s: int = 900,
    ) -> None:
        self.source_workspace = source_workspace
        self.install_root = install_root
        self.profile_root = profile_root
        self.ros_distro = ros_distro
        self.required_packages = list(required_packages or DEFAULT_BRIDGE_PACKAGES)
        self.ros_setup_path = ros_setup_path or Path(f"/opt/ros/{ros_distro}/setup.bash")
        self.command_runner = command_runner or self._run_command
        self.timeout_s = timeout_s

    def plan(self) -> dict:
        workspace_root = self._workspace_root()
        packages = self._discover_packages()
        missing_packages = [name for name in self.required_packages if name not in packages]
        colcon_path = shutil.which("colcon")
        ros_setup_exists = self.ros_setup_path.exists()
        profiles = sorted(path.name for path in self.profile_root.glob("*.yaml")) if self.profile_root and self.profile_root.exists() else []
        colcon_command = [
            "colcon",
            "--log-base",
            "log/ros2_bridge",
            "build",
            "--base-paths",
            self._base_path_arg(workspace_root),
            "--build-base",
            "build/ros2_bridge",
            "--install-base",
            "install/ros2_bridge",
            "--packages-select",
            *self.required_packages,
        ]
        shell_command = self._shell_command(workspace_root, colcon_command)
        warnings = []
        if not self.source_workspace.exists():
            warnings.append("source workspace does not exist")
        if missing_packages:
            warnings.append("one or more required bridge packages are missing")
        if not colcon_path:
            warnings.append("colcon is not available on PATH")
        if not ros_setup_exists:
            warnings.append(f"ROS setup file is missing: {self.ros_setup_path}")
        return {
            "source_workspace": str(self.source_workspace),
            "install_root": str(self.install_root),
            "profile_root": str(self.profile_root) if self.profile_root else "",
            "ros_distro": self.ros_distro,
            "ros_setup": str(self.ros_setup_path),
            "workspace_root": str(workspace_root),
            "packages": packages,
            "required_packages": list(self.required_packages),
            "missing_packages": missing_packages,
            "profiles": profiles,
            "colcon": colcon_path or "",
            "commands": [
                f"source {self.ros_setup_path}",
                f"cd {workspace_root}",
                " ".join(colcon_command),
            ],
            "subprocess_command": ["bash", "-lc", shell_command],
            "implemented": True,
            "safe_to_run": bool(self.source_workspace.exists() and not missing_packages and colcon_path and ros_setup_exists),
            "dry_run_supported": True,
            "requires_opt_in_env": "AGENTIC_ALLOW_BRIDGE_INSTALL",
            "source_commit": self._source_commit(),
            "warnings": warnings,
        }

    def validate(self) -> dict:
        plan = self.plan()
        if plan["missing_packages"]:
            return {
                "success": False,
                "error_code": "BRIDGE_REQUIRED_PACKAGES_MISSING",
                "reason": "; ".join(plan["missing_packages"]),
                "plan": plan,
            }
        if not self.source_workspace.exists():
            return {
                "success": False,
                "error_code": "BRIDGE_SOURCE_WORKSPACE_MISSING",
                "reason": "source workspace does not exist",
                "plan": plan,
            }
        return {"success": True, "plan": plan}

    def build_workspace(self, dry_run: bool = True) -> dict:
        return self.install(dry_run=dry_run)

    def activate(self) -> dict:
        self.install_root.mkdir(parents=True, exist_ok=True)
        status = self.status()
        metadata = {
            **dict(status.get("metadata") or {}),
            "success": True,
            "status": "active",
            "activated_at": _utc_now(),
        }
        self._write_status(metadata)
        return metadata

    def rollback(self) -> dict:
        self.install_root.mkdir(parents=True, exist_ok=True)
        metadata = {
            "success": True,
            "status": "rolled_back",
            "rolled_back_at": _utc_now(),
            "installed": False,
        }
        self._write_status(metadata)
        return metadata

    def status(self) -> dict:
        status_path = self.install_root / "status.json"
        metadata = {}
        if status_path.exists():
            metadata = json.loads(status_path.read_text(encoding="utf-8"))
        return {
            "success": True,
            "install_root": str(self.install_root),
            "source_workspace": str(self.source_workspace),
            "status": metadata.get("status", "not_installed"),
            "installed": bool(metadata.get("installed", False) or metadata.get("status") in {"installed", "active"}),
            "metadata": metadata,
        }

    def install(self, dry_run: bool = True) -> dict:
        plan = self.plan()
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "status": "install_planned",
                "installed": False,
                "plan": plan,
            }
        if os.environ.get("AGENTIC_ALLOW_BRIDGE_INSTALL") != "1":
            return {
                "success": False,
                "dry_run": False,
                "status": "install_blocked",
                "installed": False,
                "error_code": "BRIDGE_INSTALL_REQUIRES_OPT_IN",
                "reason": "set AGENTIC_ALLOW_BRIDGE_INSTALL=1 to run bridge install commands",
                "plan": plan,
            }
        if not plan["safe_to_run"]:
            return {
                "success": False,
                "dry_run": False,
                "status": "install_plan_unsafe",
                "installed": False,
                "error_code": "BRIDGE_INSTALL_PLAN_UNSAFE",
                "reason": "; ".join(plan["warnings"]) or "bridge install plan is not safe to run",
                "plan": plan,
            }

        started_at = _utc_now()
        completed = self.command_runner(plan["subprocess_command"], self.timeout_s)
        result = {
            "success": completed.returncode == 0,
            "dry_run": False,
            "status": "installed" if completed.returncode == 0 else "install_failed",
            "installed": completed.returncode == 0,
            "error_code": "" if completed.returncode == 0 else "BRIDGE_INSTALL_COMMAND_FAILED",
            "reason": "" if completed.returncode == 0 else "bridge install command failed",
            "build_timestamp": started_at,
            "completed_at": _utc_now(),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "plan": plan,
        }
        self._write_status(result)
        return result

    def _workspace_root(self) -> Path:
        if self.source_workspace.name == "ros2_bridge_src":
            return self.source_workspace.parent
        return self.source_workspace

    def _base_path_arg(self, workspace_root: Path) -> str:
        try:
            return str(self.source_workspace.relative_to(workspace_root))
        except ValueError:
            return str(self.source_workspace)

    def _discover_packages(self) -> list[str]:
        if not self.source_workspace.exists():
            return []
        return sorted(path.parent.name for path in self.source_workspace.glob("*/package.xml"))

    def _shell_command(self, workspace_root: Path, colcon_command: list[str]) -> str:
        return (
            "set -euo pipefail; "
            f"source {self.ros_setup_path}; "
            f"cd {workspace_root}; "
            + " ".join(colcon_command)
        )

    def _source_commit(self) -> str:
        for root in [self.source_workspace, self.source_workspace.parent]:
            if not root.exists():
                continue
            try:
                completed = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "HEAD"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if completed.returncode == 0:
                return completed.stdout.strip()
        return "unknown"

    def _run_command(self, command: list[str], timeout_s: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_s)

    def _write_status(self, result: dict[str, Any]) -> None:
        self.install_root.mkdir(parents=True, exist_ok=True)
        (self.install_root / "status.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
