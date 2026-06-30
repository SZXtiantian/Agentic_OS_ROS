from __future__ import annotations

from pathlib import Path


def test_task_graph_planner_has_no_keyword_goal_branches(runtime_src: Path):
    source = (runtime_src / "agentic_os" / "kernel" / "scheduler" / "task_graph_planner.py").read_text(encoding="utf-8")

    assert 'if "cup"' not in source
    assert 'if "巡检"' not in source
    assert "rule planner" not in source.lower()
    assert "hardcoded JSON plan" not in source
