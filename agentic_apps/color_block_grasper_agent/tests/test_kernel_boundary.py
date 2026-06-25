from __future__ import annotations

import ast
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]


def test_main_uses_agent_context_and_kernel_skill_contracts():
    source = (APP_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "AgentContext" in source
    assert "ctx.llm.chat_json" in source
    assert "ctx.kernel.skill.call" in source
    assert '"perception.detect_color_block"' in source
    assert '"perception.verify_held_color_block"' in source
    assert '"manipulation.pick_color_block"' in source
    assert '"manipulation.place_color_block"' in source
    assert "_normalize_task" not in source
    assert 'kwargs.get("color")' not in source
    assert 'kwargs.get("place_target")' not in source
    assert "rule_based" not in source
    assert "OpenAICompatibleChatClient" not in source
    assert "AGENTIC_LLM_API_KEY" not in source
    assert "import re" not in source
    assert any(isinstance(node, ast.AsyncFunctionDef) and node.name == "run" for node in ast.walk(tree))


def test_main_has_no_forbidden_middleware_imports_or_legacy_imports():
    tree = ast.parse((APP_DIR / "main.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = {
        "rclpy",
        "ros2_bridge_src",
        "moveit",
        "nav2",
        "geometry_msgs",
        "sensor_msgs",
        "std_msgs",
        "action_msgs",
        "hardware_interface",
        "color_block_grasper",
        "color_block_grasp",
        "block_grasper",
    }
    assert not any(any(name == item or name.startswith(f"{item}.") for item in forbidden) for name in imported)
