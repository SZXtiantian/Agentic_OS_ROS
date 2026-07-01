import pytest

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.errors import SchemaInvalidError
from agentic_runtime.skill_registry import SkillRegistry
from agentic_runtime.skill_registry.skill_manifest import extract_agentic_skill_metadata, validate_skill_manifest_dict


def test_loads_all_foundation_skills():
    config = RuntimeConfig.load()
    registry = SkillRegistry(config.skill_provider_root, app_root=config.app_root).load()
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
    assert registry.get_skill("robot.navigate_to").implementation["bridge"] == "navigation_bridge_node"
    assert registry.get_skill("navigate_to").implementation["bridge"] == "navigation_bridge_node"
    assert registry.get_skill("arm.move_named").implementation["bridge"] == "manipulation_bridge_node"
    assert registry.get_skill("perception.detect_color_block").implementation["availability"] == "real_bridge_required"
    assert registry.get_skill("manipulation.pick_color_block").access == {
        "required": True,
        "resource_type": "robot_motion",
        "irreversible": True,
    }


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


def test_skill_markdown_requires_agentic_skill_block(tmp_path):
    root = tmp_path / "system_skills"
    skill_dir = root / "utility.test"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# robot.test\n\nNo metadata here.\n", encoding="utf-8")

    with pytest.raises(SchemaInvalidError, match="missing json agentic-skill metadata block"):
        SkillRegistry(root).load()


def test_skill_markdown_rejects_invalid_json_metadata(tmp_path):
    root = tmp_path / "system_skills"
    skill_dir = root / "robot.test"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# robot.test\n\n```json agentic-skill\n{bad json}\n```\n", encoding="utf-8")

    with pytest.raises(SchemaInvalidError, match="invalid json agentic-skill metadata"):
        SkillRegistry(root).load()


def test_markdown_body_does_not_change_runtime_contract(tmp_path):
    root = tmp_path / "system_skills"
    skill_dir = root / "robot.test"
    skill_dir.mkdir(parents=True)
    markdown = """# utility.test

```json agentic-skill
{
  "schema_version": 1,
  "name": "utility.test",
  "scope": "system",
  "access": {"required": false},
  "implementation": {"type": "python", "entrypoint": "impl:run"},
  "input_schema": {"type": "object"},
  "output_schema": {"type": "object"}
}
```

## Implementation

This prose says implementation.type is ros2_action, but Runtime must ignore prose.
"""
    (skill_dir / "SKILL.md").write_text(markdown, encoding="utf-8")

    registry = SkillRegistry(root).load()

    assert registry.get_skill("utility.test").implementation == {"type": "python", "entrypoint": "impl:run"}
    assert extract_agentic_skill_metadata(markdown)["implementation"]["type"] == "python"


def test_app_skills_are_loaded_for_current_app_only():
    config = RuntimeConfig.load()
    registry = SkillRegistry(config.skill_provider_root, app_root=config.app_root).load()

    loaded = registry.load_app_skills("color_block_grasper_agent", config.app_root / "color_block_grasper_agent")

    assert {skill.name for skill in loaded} == {"app.find_best_block"}
    assert registry.get_skill("app.find_best_block", app_id="color_block_grasper_agent").scope == "app"
    with pytest.raises(KeyError):
        registry.get_skill("app.find_best_block", app_id="hello_world_agent")


def test_app_skill_must_use_app_prefix(tmp_path):
    app_root = tmp_path / "apps"
    skill_dir = app_root / "bad_app" / "skills" / "bad"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        """# bad.name

```json agentic-skill
{
  "schema_version": 1,
  "name": "bad.name",
  "scope": "app",
  "access": {"required": false},
  "implementation": {"type": "python", "entrypoint": "impl:run"},
  "input_schema": {"type": "object"},
  "output_schema": {"type": "object"}
}
```
""",
        encoding="utf-8",
    )
    registry = SkillRegistry(RuntimeConfig.load().skill_provider_root, app_root=app_root).load()

    with pytest.raises(SchemaInvalidError, match="app skill name must start with app."):
        registry.load_app_skills("bad_app")


def test_app_skill_path_escape_is_rejected(tmp_path):
    app_root = tmp_path / "apps"
    app_dir = app_root / "bad_app"
    outside = tmp_path / "outside"
    (outside / "evil").mkdir(parents=True)
    (app_dir / "skills").mkdir(parents=True)
    (outside / "evil" / "SKILL.md").write_text(
        """# app.evil

```json agentic-skill
{
  "schema_version": 1,
  "name": "app.evil",
  "scope": "app",
  "access": {"required": false},
  "implementation": {"type": "python", "entrypoint": "impl:run"},
  "input_schema": {"type": "object"},
  "output_schema": {"type": "object"}
}
```
""",
        encoding="utf-8",
    )
    (app_dir / "skills" / "evil").symlink_to(outside / "evil")
    registry = SkillRegistry(RuntimeConfig.load().skill_provider_root, app_root=app_root).load()

    with pytest.raises(SchemaInvalidError, match="app skill path escapes app root"):
        registry.load_app_skills("bad_app")
