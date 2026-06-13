#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


FORBIDDEN_PATTERNS = [
    "import rclpy",
    "from rclpy",
    "/cmd_vel",
    "/scan",
    "/odom",
    "/tf",
    "NavigateToPose",
    "MoveGroup",
    "ActionClient",
    "create_publisher",
    "create_subscription",
]

SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_SRC = SCRIPT_DIR.parent
WORKSPACE_SRC = RUNTIME_SRC.parent

SCAN_ROOTS = [
    RUNTIME_SRC / "agentic_os",
    RUNTIME_SRC / "agentic_runtime",
    RUNTIME_SRC / "agentic_runtime" / "sdk",
    WORKSPACE_SRC / "inspection_agent",
    WORKSPACE_SRC / "room_inspection_app",
    WORKSPACE_SRC / "pickup_agent",
    WORKSPACE_SRC / "laundry_agent",
    WORKSPACE_SRC / "robotic_coding_agent",
    WORKSPACE_SRC / "robotops_agent",
    WORKSPACE_SRC / "app_template",
]

TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".md", ".txt"}


def should_scan(path: Path) -> bool:
    if "__pycache__" in path.parts:
        return False
    if path.name.startswith("."):
        return False
    return path.suffix in TEXT_SUFFIXES


def main() -> int:
    failures: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not should_scan(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in text:
                    failures.append(f"{path}: forbidden pattern {pattern!r}")

    if failures:
        print("Forbidden ROS2 access detected:")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("forbidden import/static guard ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
