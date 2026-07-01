from __future__ import annotations

from pathlib import Path


REQUIRED_DOCS = [
    "kernel_syscalls.md",
    "runtime_real_only.md",
    "provider_contracts.md",
    "access_audit.md",
    "real_integration.md",
    "errors.md",
]


def test_real_only_foundation_docs_exist(runtime_src: Path):
    for name in REQUIRED_DOCS:
        path = runtime_src / "docs" / name
        assert path.exists(), name
        assert path.read_text(encoding="utf-8").strip(), name


def test_provider_docs_do_not_claim_reserved_modes_available(runtime_src: Path):
    docs = (runtime_src / "docs" / "provider_contracts.md").read_text(encoding="utf-8")

    assert "| ROS bridge | `cli` when `ros2` CLI is present |" in docs
    assert "`http`" in docs and "`websocket`" in docs
    assert "only when configured" in docs
    assert "`semantic_vector`" in docs
    assert "available" not in docs.split("| ROS bridge |", 1)[1].split("\n", 1)[0].lower()


def test_runtime_docs_state_no_simulated_runtime_surface(runtime_src: Path):
    docs = (runtime_src / "docs" / "runtime_real_only.md").read_text(encoding="utf-8").lower()

    assert "do not provide a" in docs
    assert "simulated runtime mode" in docs
    assert "task_input_field_unsupported" in docs


def test_runtime_real_only_docs_describe_scheduler_capability_and_cup_gaps(runtime_src: Path):
    docs = (runtime_src / "docs" / "runtime_real_only.md").read_text(encoding="utf-8")

    assert "env_aware_priority_dag" in docs
    assert "KernelService.execute_request" in docs
    assert "ROS_SERVICE_UNAVAILABLE" in docs
    assert "ROS_ACTION_UNAVAILABLE" in docs
    assert "required=/agentic/robot/get_state" in docs
    assert "visible_services=0" in docs
    assert "command=ros2 service list" in docs
    assert "start_command=ros2 run agentic_capability_bridge state_bridge_node" in docs
    assert "bridge_executable=agentic_capability_bridge/state_bridge_node:available" in docs
    assert "executable_command=ros2 pkg executables agentic_capability_bridge" in docs
    assert "AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE=1" in docs
    assert "AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS" in docs
    assert "auto_start_readonly_state_bridge=" in docs
    assert "ros_graph=" in docs
    assert "profile_dependencies=" in docs
    assert "AGENTIC_VERIFY_BRIDGE_PROFILE_FILE" in docs
    assert "camera_launch_files_present=" in docs
    assert "camera_backend=" in docs
    assert "arm_backend=" in docs
    assert "gripper_backend=" in docs
    assert "next_backend_steps=" in docs
    assert "backend_step_hints=" in docs
    assert "operator-gated" in docs
    assert "cup_pose" in docs
    assert "generic cup detection" in docs
