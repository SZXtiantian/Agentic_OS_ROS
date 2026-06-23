from __future__ import annotations

from pathlib import Path


BRIDGE_CODE_SUFFIXES = {".py", ".yaml", ".yml"}


def _bridge_source_files(repo_root: Path) -> list[Path]:
    bridge_root = repo_root / "ros2_bridge_src"
    files: list[Path] = []
    for path in bridge_root.rglob("*"):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        if path.suffix in BRIDGE_CODE_SUFFIXES:
            files.append(path)
    return sorted(files)


def test_ros2_bridge_code_has_no_simulated_navigation_success_path(repo_root):
    failures: list[str] = []
    disallowed = [
        "mock_nav",
        "mock_duration_s",
        "_execute_mock",
        '"mode": "mock"',
        "'mode': 'mock'",
        '"mock_robot"',
        "'mock_robot'",
    ]
    for path in _bridge_source_files(repo_root):
        rel = path.relative_to(repo_root)
        text = path.read_text(encoding="utf-8")
        for pattern in disallowed:
            if pattern in text:
                failures.append(f"{rel}: {pattern}")

    assert failures == []


def test_navigation_bridge_reports_real_backend_dependency_errors(repo_root):
    source = (
        repo_root
        / "ros2_bridge_src"
        / "agentic_capability_bridge"
        / "agentic_capability_bridge"
        / "navigation_bridge_node.py"
    ).read_text(encoding="utf-8")

    assert "def _execute_mock" not in source
    assert "return self._execute_nav2(goal_handle)" in source
    assert "ROS_BRIDGE_UNAVAILABLE" in source
    assert "ROS_SERVICE_UNAVAILABLE" in source
    assert "ROS_ACTION_TIMEOUT" in source


def test_state_bridge_defaults_to_real_identity_and_fails_when_no_backend_visible(repo_root):
    source = (
        repo_root
        / "ros2_bridge_src"
        / "agentic_capability_bridge"
        / "agentic_capability_bridge"
        / "state_bridge_node.py"
    ).read_text(encoding="utf-8")

    assert 'self.declare_parameter("robot_id", "real_robot")' in source
    assert 'self.declare_parameter("mode", "real_bridge")' in source
    assert "ROS_BRIDGE_PROFILE_UNAVAILABLE" in source
    assert "ROS_BRIDGE_UNAVAILABLE" in source
    assert "response.success = not error_code" in source


def test_aggregate_bridge_readme_does_not_document_legacy_simulated_runtime(repo_root):
    readme = (repo_root / "ros2_bridge_src" / "agentic_app_runtime_bridge" / "README.md").read_text(encoding="utf-8")

    assert "mock-only" not in readme
    assert "MVP mock Runtime" not in readme
