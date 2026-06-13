from __future__ import annotations

from pathlib import Path

from agentic_runtime.types import AppManifest


FORBIDDEN_APP_PATTERNS = [
    "import " + "rclpy",
    "from " + "rclpy",
    "/" + "cmd_vel",
    "/" + "scan",
    "/" + "odom",
    "/" + "tf",
    "Navigate" + "ToPose",
    "Move" + "Group",
    "Action" + "Client",
    "create_" + "publisher",
    "create_" + "subscription",
]


class AppValidationError(ValueError):
    pass


class AppValidator:
    def validate(self, app_dir: Path, manifest: AppManifest) -> None:
        if not manifest.entrypoint or ":" not in manifest.entrypoint:
            raise AppValidationError("app entrypoint must be module:function")
        module_name, _ = manifest.entrypoint.split(":", 1)
        module_path = app_dir / f"{module_name}.py"
        if not module_path.exists():
            raise AppValidationError(f"app entrypoint module missing: {module_path}")
        text = module_path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_APP_PATTERNS:
            if pattern in text:
                raise AppValidationError(f"forbidden robot/ROS2 access in app source: {pattern}")
