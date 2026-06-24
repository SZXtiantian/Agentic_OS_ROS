import pytest

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.skill_registry.skill_manifest import validate_skill_manifest_dict


def test_loads_all_foundation_skills():
    registry = SkillRegistry(RuntimeConfig.load().skill_root).load()
    names = {skill.name for skill in registry.list_skills()}
    assert {
        "robot.get_state",
        "world.resolve_place",
        "robot.navigate_to",
        "robot.inspect_area",
        "perception.observe",
        "arm.get_state",
        "arm.move_named",
        "gripper.set",
        "robot.stop",
        "memory.remember",
        "memory.recall",
        "human.ask",
        "report.say",
        "perception.detect_color_block",
        "manipulation.pick_color_block",
        "manipulation.place_color_block",
    } <= names
    assert registry.get_skill("robot.navigate_to").backend["bridge"] == "navigation_bridge_node"
    assert registry.get_skill("navigate_to").backend["bridge"] == "navigation_bridge_node"
    assert registry.get_skill("arm.move_named").backend["bridge"] == "manipulation_bridge_node"
    assert registry.get_skill("perception.detect_color_block").backend["availability"] == "real_bridge_required"


def test_missing_name_fails():
    with pytest.raises(SchemaInvalidError):
        validate_skill_manifest_dict({"permission_requirements": [], "backend": {}, "input_schema": {}, "output_schema": {}})


def test_missing_permissions_fails():
    with pytest.raises(SchemaInvalidError):
        validate_skill_manifest_dict({"name": "x", "version": "0", "backend": {}, "input_schema": {}, "output_schema": {}})


def test_simulated_skill_backend_manifest_fails_fast():
    manifest = {
        "name": "human.ask",
        "version": "0",
        "input_schema": {},
        "output_schema": {},
        "permission_requirements": ["human.ask"],
        "resource_requirements": {"locks": []},
        "backend": {"type": "mock"},
    }

    with pytest.raises(SchemaInvalidError, match="simulated skill backend type 'mock' is disabled"):
        validate_skill_manifest_dict(manifest)
