from pathlib import Path

from scripts import check_no_runtime_rclpy_imports


def test_current_runtime_and_kernel_have_no_rclpy_imports(runtime_src):
    assert check_no_runtime_rclpy_imports.scan(runtime_src) == []


def test_rclpy_import_guard_ignores_ros2_bridge_src(tmp_path):
    runtime_src = tmp_path / "agentic_runtime_src"
    (runtime_src / "agentic_os").mkdir(parents=True)
    (runtime_src / "agentic_runtime").mkdir(parents=True)
    (runtime_src / "agentic_os" / "kernel.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "ros2_bridge_src").mkdir()
    (tmp_path / "ros2_bridge_src" / "bridge.py").write_text("import rclpy\n", encoding="utf-8")

    assert check_no_runtime_rclpy_imports.scan(runtime_src) == []


def test_rclpy_import_guard_detects_runtime_import(tmp_path):
    runtime_src = tmp_path / "agentic_runtime_src"
    offender = runtime_src / "agentic_runtime" / "bad.py"
    offender.parent.mkdir(parents=True)
    offender.write_text("from rclpy.node import Node\n", encoding="utf-8")

    assert check_no_runtime_rclpy_imports.scan(runtime_src) == [offender]
