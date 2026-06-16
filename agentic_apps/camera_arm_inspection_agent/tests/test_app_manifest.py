from pathlib import Path

import yaml


def test_manifest_uses_agenticos_capabilities_only():
    manifest = yaml.safe_load((Path(__file__).parents[1] / "app.yaml").read_text(encoding="utf-8"))
    assert "perception.observe" in manifest["required_capabilities"]
    assert "arm.move_named" in manifest["required_capabilities"]
    assert "gripper.set" in manifest["required_capabilities"]
    assert "robot.move" not in manifest["permissions"]
