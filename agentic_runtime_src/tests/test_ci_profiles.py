from pathlib import Path


def test_pytest_markers_define_portable_integration_ros2_hardware(runtime_src):
    pyproject = (runtime_src / "pyproject.toml").read_text(encoding="utf-8")

    assert '"portable: no network, no ROS2, no hardware"' in pyproject
    assert '"integration: opt-in real integration contracts; skip as UNVERIFIED when real dependencies are absent"' in pyproject
    assert '"ros2: requires ROS2 environment"' in pyproject
    assert '"hardware: requires real robot hardware"' in pyproject


def test_run_tests_defaults_to_portable_profile(runtime_src):
    script = (runtime_src / "scripts" / "run_tests.sh").read_text(encoding="utf-8")

    assert 'PYTEST_MARK_EXPR="${PYTEST_MARK_EXPR:-not integration and not ros2 and not hardware}"' in script
    assert 'pytest -m "$PYTEST_MARK_EXPR" -q' in script


def test_real_robot_scripts_remain_outside_default_pytest_collection(runtime_src):
    real_robot_scripts = sorted(Path(runtime_src / "scripts").glob("real_robot_*.sh"))

    assert real_robot_scripts
    assert all(path.suffix == ".sh" for path in real_robot_scripts)
