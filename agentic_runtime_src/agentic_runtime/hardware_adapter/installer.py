from __future__ import annotations

from pathlib import Path


class BridgeInstaller:
    def __init__(self, source_workspace: Path, install_root: Path) -> None:
        self.source_workspace = source_workspace
        self.install_root = install_root

    def plan(self) -> dict:
        return {
            "source_workspace": str(self.source_workspace),
            "install_root": str(self.install_root),
            "implemented": False,
            "reason": "real ROS2/Nav2 bridge build is deferred until the mock kernel/session path is complete",
        }
