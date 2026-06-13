import pytest

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.skill_registry.skill_manifest import validate_skill_manifest_dict


def test_loads_all_mvp_skills():
    registry = SkillRegistry(RuntimeConfig.load().skill_root).load()
    assert len(registry.list_skills()) == 9
    assert registry.get_skill("robot.navigate_to").backend["bridge"] == "navigation_bridge_node"
    assert registry.get_skill("navigate_to").backend["bridge"] == "navigation_bridge_node"


def test_missing_name_fails():
    with pytest.raises(SchemaInvalidError):
        validate_skill_manifest_dict({"permission_requirements": [], "backend": {}, "input_schema": {}, "output_schema": {}})


def test_missing_permissions_fails():
    with pytest.raises(SchemaInvalidError):
        validate_skill_manifest_dict({"name": "x", "version": "0", "backend": {}, "input_schema": {}, "output_schema": {}})
