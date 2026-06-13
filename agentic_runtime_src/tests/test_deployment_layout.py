from pathlib import Path


def install_root() -> Path:
    opt = Path("/opt/agentic")
    if opt.exists():
        return opt
    return Path("/home/ubuntu/staging_opt_agentic")


def test_deployment_layout_exists():
    assert Path("/opt/ros/humble").exists() or Path("/opt/ros").exists()
    assert install_root().exists()
    assert Path("/home/ubuntu/ros2_ws").exists()
    assert Path("/home/ubuntu/agentic_ws").exists()
    assert Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src").exists()
    assert Path("/home/ubuntu/agentic_ws/src/inspection_agent").exists()
    assert not Path("/home/ubuntu/ros2_ws/src/agentic_msgs").exists()
    assert not Path("/home/ubuntu/ros2_ws/src/agentic_capability_bridge").exists()
    assert Path("/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_msgs").exists()
    assert Path("/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_capability_bridge").exists()
    assert (install_root() / "bridges" / "ros2").is_dir()
    assert (install_root() / "etc" / "bridge_profiles").is_dir()
