from __future__ import annotations

from pathlib import Path

import yaml
from agentic_runtime.skill_registry.skill_manifest import extract_agentic_skill_metadata


REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = Path(__file__).resolve().parents[1]


def test_manifest_declares_native_color_block_capabilities():
    manifest = yaml.safe_load((APP_DIR / "app.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "color_block_grasper_agent"
    assert manifest["entrypoint"] == "main:run"
    assert {
        "llm.external.call",
        "perception.detect.color_block",
        "perception.center.color_block",
        "perception.verify.color_block_held",
        "manipulation.pick.color_block",
        "manipulation.place.color_block",
        "human.ask",
        "report.say",
    } <= set(manifest["permissions"])
    assert {
        "agenticos.runtime.llm_chat",
        "llm.chat",
        "perception.detect_color_block",
        "perception.center_color_block",
        "perception.verify_held_color_block",
        "manipulation.pick_color_block",
        "manipulation.place_color_block",
        "kernel.skill",
    } <= set(manifest["required_capabilities"])
    assert manifest["safety_policy"]["allow_manipulation"] is True
    assert manifest["runtime_limits"]["llm_planning_enabled"] is True
    assert manifest["runtime_limits"]["llm_planning_provider"] == "agenticos.runtime.llm_chat"


def test_color_block_skill_contracts_are_real_bridge_contracts():
    skill_root = REPO_ROOT / "agentic_runtime_src" / "system_skills"
    expected = {
        "perception.detect_color_block": ("perception.detect_color_block", "ros2_service"),
        "perception.center_color_block": ("perception.center_color_block", "ros2_service"),
        "perception.verify_held_color_block": ("perception.verify_held_color_block", "ros2_service"),
        "manipulation.pick_color_block": ("manipulation.pick_color_block", "ros2_action"),
        "manipulation.place_color_block": ("manipulation.place_color_block", "ros2_action"),
    }
    for dirname, (name, implementation_type) in expected.items():
        data = extract_agentic_skill_metadata((skill_root / dirname / "SKILL.md").read_text(encoding="utf-8"))
        assert data["name"] == name
        assert data["implementation"]["type"] == implementation_type
        assert data["implementation"]["availability"] == "real_bridge_required"
        assert data["resource_requirements"]["locks"]
        assert data["observability"]["audit"] is True
