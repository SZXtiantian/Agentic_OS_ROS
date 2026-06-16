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


def test_real_robot_acceptance_reports_bringup_and_usb_diagnostics():
    script = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_camera_acceptance.sh").read_text(
        encoding="utf-8"
    )
    assert "ROBOT_BRINGUP_NOT_RUNNING" in script
    assert "CAMERA_USB_DEVICE_MISSING" in script
    assert "ROS_GRAPH_DDS_LOCATOR_STALE" in script
    assert "--no-daemon" in script
    assert "3251:1930" in script
    assert "AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1" in script


def test_real_robot_multi_angle_acceptance_uses_arm_health_gate():
    health_gate = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_health_gate.sh").read_text(
        encoding="utf-8"
    )
    multi_angle = Path(
        "/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_multi_angle_photo_acceptance.sh"
    ).read_text(encoding="utf-8")

    assert "ARM_SERVO_ID3_POSITION_INVALID" in health_gate
    assert "ARM_TORQUE_DISABLED_OR_UNVERIFIED" in health_gate
    assert "ARM_HEALTH_GATE_FAILED" in health_gate
    assert "ARM_SERIAL_PORT_MULTI_OWNER" in health_gate
    assert "button_scan.service" in health_gate
    assert "next_allowed_stage" in health_gate
    assert "blocked_motion_tests" in health_gate
    assert "hardware_repair_required" in health_gate
    assert "torque_semantics_required" in health_gate
    assert "gripper_minimal_motion" in health_gate
    assert "/ros_robot_controller/bus_servo/get_state" in health_gate
    assert "bus_servo/set_position" not in health_gate
    assert "arm_health_gate" in multi_angle
    assert "check_camera_pose_action_groups.py" in multi_angle
    assert "refusing real multi-angle arm motion" in multi_angle
    assert "camera_pitch_down_15" not in multi_angle


def test_real_robot_torque_semantics_probe_is_gated_and_no_position_motion():
    probe = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_torque_semantics_probe.sh").read_text(
        encoding="utf-8"
    )

    assert "AGENTIC_ARM_TORQUE_PROBE_ALLOW_STATE_CHANGE" in probe
    assert "TORQUE_SEMANTICS_PROBE_READ_ONLY" in probe
    assert "TORQUE_SEMANTICS_INCONCLUSIVE" in probe
    assert "/ros_robot_controller/bus_servo/get_state" in probe
    assert "/ros_robot_controller/bus_servo/set_state" in probe
    assert "bus_servo/set_position" not in probe
    assert "This probe never sends servo positions" in probe


def test_real_robot_gripper_minimal_motion_is_gated_and_id10_only():
    script = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_gripper_minimal_motion.sh").read_text(
        encoding="utf-8"
    )

    assert "AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION" in script
    assert "AGENTIC_ARM_TORQUE_STATE_VERIFIED" in script
    assert "AGENTIC_ARM_EXPECTED_TORQUE_STATE" in script
    assert "SERVO_ID=10" in script
    assert "POSITIONS=(500 540 500)" in script
    assert "/ros_robot_controller/bus_servo/set_position" in script
    assert "/servo_controller" not in script
    assert "GRIPPER_POSITION_READBACK_MISMATCH" in script
    assert "ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED" in script


def test_real_robot_action_group_probe_is_gated_and_uses_agenticos_bridge():
    script = Path(
        "/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_action_group_probe.sh"
    ).read_text(encoding="utf-8")

    assert "AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION" in script
    assert "ARM_MOTION_DISABLED" in script
    assert "/agentic/arm/move_named" in script
    assert "/ros_robot_controller/bus_servo/get_state" in script
    assert "ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED" in script
    assert "probe_left_up" in script
    assert "probe_right_down" in script
    assert "/ros_robot_controller/bus_servo/set_position" not in script
    assert "ros2 topic pub" not in script


def test_camera_pose_action_group_semantic_guard_blocks_unsafe_backends():
    script = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/check_camera_pose_action_groups.py").read_text(
        encoding="utf-8"
    )

    assert "CAMERA_POSE_BACKEND_SEMANTICALLY_UNSAFE" in script
    assert "CAMERA_POSE_BACKEND_OPERATES_GRIPPER" in script
    assert "left_down" in script
    assert "right_down" in script
    assert "MAX_GRIPPER_DELTA" in script


def test_agentic_entrypoint_supports_environment_and_natural_language_shell():
    installer = Path("/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh").read_text(
        encoding="utf-8"
    )

    assert "source /opt/ros/humble/setup.bash" in installer
    assert "source /home/ubuntu/agentic_ws/install/ros2_bridge/setup.bash" in installer
    assert 'if [ "${1:-}" = "enter" ]' in installer
    assert 'if [ "${1:-}" = "chat" ]' in installer
    assert "python -m agentic_runtime.nl_gateway" in installer
    assert "var/tasks" in installer
