from pathlib import Path

import yaml


def test_app_manifest_has_required_fields():
    path = Path(__file__).resolve().parents[1] / "app.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["name"] == "room_inspection_app"
    assert "robot.move" in data["permissions"]
    assert "robot.navigate_to" in data["required_capabilities"]
    assert data["safety_policy"]["allow_manipulation"] is False
