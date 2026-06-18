#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from pathlib import Path


def _default_runtime_src() -> Path:
    return Path(__file__).resolve().parents[1]


def _imports_rclpy(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "rclpy" or alias.name.startswith("rclpy."):
                    return True
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "rclpy" or module.startswith("rclpy."):
                return True
    return False


def scan(runtime_src: Path) -> list[Path]:
    failures: list[Path] = []
    for root in [runtime_src / "agentic_os", runtime_src / "agentic_runtime"]:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _imports_rclpy(path):
                failures.append(path)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject rclpy imports outside ROS2 bridge source packages.")
    parser.add_argument("--runtime-src", type=Path, default=_default_runtime_src())
    args = parser.parse_args(argv)

    runtime_src = args.runtime_src.expanduser().resolve()
    failures = scan(runtime_src)
    if failures:
        print("Forbidden rclpy imports detected outside ros2_bridge_src:")
        for path in failures:
            print(f"  {path}")
        return 1
    print("runtime/kernel rclpy import guard ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
