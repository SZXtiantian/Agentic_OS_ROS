#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from pathlib import Path


FORBIDDEN_IMPORT_ROOTS = {
    "openai",
    "litellm",
    "vllm",
    "rclpy",
    "ros2_bridge_src",
    "moveit",
    "moveit_commander",
    "nav2",
    "nav2_simple_commander",
    "geometry_msgs",
    "sensor_msgs",
    "std_msgs",
    "action_msgs",
    "hardware_interface",
    "agentic_runtime.llm.client",
}
FORBIDDEN_RUNTIME_STRINGS = [
    "/cmd_vel",
    "/scan",
    "/odom",
    "/tf",
    "MoveGroup",
    "NavigateToPose",
    "ActionClient",
    "create_publisher",
    "create_subscription",
    "OpenAICompatibleChatClient",
    "AGENTIC_LLM_API_KEY",
    "load_llm_config",
    "agentic_runtime.llm.client",
]
LEGACY_IMPORT_ROOTS = {
    "color_block_grasper",
    "color_block_grasp",
    "block_grasper",
}
LEGACY_RUNTIME_STRINGS = [
    "ros2 run color_block_grasper",
    "color_block_grasp_cli",
    "color_block_place_cli",
    "color_block_grasper_node",
    "/home/ubuntu/ros2_ws/src/color_block_grasper",
    "/home/ubuntu/agentic_ws/src/color_block_grasper_agent/entry.py",
]


def _is_test_file(path: Path) -> bool:
    return "tests" in path.parts or path.name.startswith("test_")


def _module_matches(module: str, roots: set[str]) -> bool:
    return any(module == root or module.startswith(f"{root}.") for root in roots)


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def _iter_string_literals(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def scan(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.exists():
        return [f"SCAN_ROOT_MISSING: {root}"]
    python_files = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    for path in python_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            errors.append(f"{path}: PYTHON_SYNTAX_ERROR: {exc}")
            continue

        for module in _iter_imports(tree):
            if _module_matches(module, FORBIDDEN_IMPORT_ROOTS):
                errors.append(f"{path}: FORBIDDEN_IMPORT: {module}")
            if "color_block_grasper_agent" in path.parts and _module_matches(module, LEGACY_IMPORT_ROOTS):
                errors.append(f"{path}: LEGACY_COLOR_BLOCK_IMPORT: {module}")

        if _is_test_file(path):
            continue

        text = path.read_text(encoding="utf-8")
        if path.name == "main.py" and (
            "hello_world_agent" in path.parts or "color_block_grasper_agent" in path.parts
        ):
            if "ctx.llm.chat_json" not in text:
                errors.append(f"{path}: SYSTEM_LLM_FACADE_MISSING: ctx.llm.chat_json")
            if "rule_based" in text:
                errors.append(f"{path}: RULE_BASED_TUTORIAL_PLANNER_FORBIDDEN")
        if path.name == "main.py" and "color_block_grasper_agent" in path.parts:
            for pattern in (
                "_normalize_task",
                'kwargs.get("color")',
                "kwargs.get('color')",
                'kwargs.get("place_target")',
                "kwargs.get('place_target')",
                "re.search",
                "re.match",
                "re.compile",
            ):
                if pattern in text:
                    errors.append(f"{path}: COLOR_BLOCK_KEYWORD_OR_STRUCTURED_PLANNER_FORBIDDEN: {pattern}")

        for value in _iter_string_literals(tree):
            for pattern in FORBIDDEN_RUNTIME_STRINGS:
                if pattern in value:
                    errors.append(f"{path}: FORBIDDEN_RUNTIME_INTERFACE: {pattern}")
            if "color_block_grasper_agent" in path.parts:
                for pattern in LEGACY_RUNTIME_STRINGS:
                    if pattern in value:
                        errors.append(f"{path}: LEGACY_COLOR_BLOCK_RUNTIME_DEPENDENCY: {pattern}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject direct ROS2, MoveIt, Nav2, bridge, and legacy app dependencies in Agentic Apps.")
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    errors = scan(args.root)
    if errors:
        print("AGENTIC_APP_BOUNDARY_CHECK_FAILED")
        for error in errors:
            print(error)
        return 1
    print(f"AGENTIC_APP_BOUNDARY_CHECK_OK root={args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
