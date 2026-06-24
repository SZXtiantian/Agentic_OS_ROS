from __future__ import annotations

import ast
from pathlib import Path

import yaml


APP_DIR = Path(__file__).resolve().parents[1]


def test_hello_world_keeps_template_core_files():
    expected = [
        "README.md",
        "app.yaml",
        "main.py",
        "prompts/system.md",
        "storage/.gitkeep",
        "workflows/default.yaml",
    ]
    for rel in expected:
        assert (APP_DIR / rel).exists(), rel
    marker = (APP_DIR / ".agentic_template_source").read_text(encoding="utf-8")
    assert "source=agentic_apps/app_template" in marker
    assert "template_name=app_template" in marker


def test_hello_world_manifest_entrypoint_and_capabilities():
    manifest = yaml.safe_load((APP_DIR / "app.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "hello_world_agent"
    assert manifest["entrypoint"] == "main:run"
    assert {
        "kernel.context",
        "kernel.memory",
        "kernel.storage",
        "kernel.tool",
        "kernel.skill",
        "report.say",
    } <= set(manifest["required_capabilities"])


def test_hello_world_main_uses_agent_context_without_robot_middleware_imports():
    source = (APP_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "AgentContext" in source
    assert any(isinstance(node, ast.AsyncFunctionDef) and node.name == "run" for node in ast.walk(tree))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = {"rclpy", "ros2_bridge_src", "moveit", "nav2", "geometry_msgs", "sensor_msgs", "std_msgs"}
    assert not any(any(name == item or name.startswith(f"{item}.") for item in forbidden) for name in imported)
