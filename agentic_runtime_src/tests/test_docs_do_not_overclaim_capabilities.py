from __future__ import annotations

from pathlib import Path


def test_provider_docs_classify_unimplemented_modes_as_reserved_or_unsupported(runtime_src: Path):
    docs = (runtime_src / "docs" / "provider_contracts.md").read_text(encoding="utf-8")

    ros_row = next(line for line in docs.splitlines() if line.startswith("| ROS bridge |"))
    human_row = next(line for line in docs.splitlines() if line.startswith("| Human |"))
    llm_row = next(line for line in docs.splitlines() if line.startswith("| LLM |"))

    assert "`cli`" in ros_row
    for mode in ("`service`", "`action`", "`topic`", "`http`", "`websocket`"):
        assert mode in ros_row.split("|")[-2]
    assert "`file_queue`" in human_row
    assert "`console`" in human_row.split("|")[-2]
    assert "`local`" in llm_row.split("|")[-2]
    assert "`huggingface`" in llm_row.split("|")[-2]


def test_real_integration_docs_use_unverified_dependency_language(runtime_src: Path):
    docs = (runtime_src / "docs" / "real_integration.md").read_text(encoding="utf-8")

    assert "UNVERIFIED_REAL_DEPENDENCY" in docs
    assert "must not be replaced by simulated success" in docs


def test_real_integration_docs_describe_scheduler_capability_preflight_diagnostics(runtime_src: Path):
    docs = (runtime_src / "docs" / "real_integration.md").read_text(encoding="utf-8")

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


def test_root_readmes_describe_scheduler_capability_dependency_gap(repo_root: Path):
    english = (repo_root / "README.md").read_text(encoding="utf-8")
    chinese = (repo_root / "README.zh-CN.md").read_text(encoding="utf-8")

    for docs in (english, chinese):
        assert "UNVERIFIED_REAL_DEPENDENCY" in docs
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
        assert "ros_graph=" in docs
        assert "profile_dependencies=" in docs
        assert "camera_launch_files_present=" in docs
        assert "camera_backend=" in docs
        assert "arm_backend=" in docs
        assert "gripper_backend=" in docs
        assert "next_backend_steps=" in docs
        assert "backend_step_hints=" in docs
    assert "generic cup" in english
    assert "通用水杯" in chinese
