from __future__ import annotations

from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]


def test_color_block_app_keeps_template_core_files():
    for rel in [
        "README.md",
        "app.yaml",
        "main.py",
        "prompts/system.md",
        "storage/.gitkeep",
        "workflows/default.yaml",
    ]:
        assert (APP_DIR / rel).exists(), rel
    assert (APP_DIR / "tests").is_dir()


def test_color_block_app_has_template_source_marker():
    marker = (APP_DIR / ".agentic_template_source").read_text(encoding="utf-8")
    assert "source=agentic_apps/app_template" in marker
    assert "template_name=app_template" in marker
