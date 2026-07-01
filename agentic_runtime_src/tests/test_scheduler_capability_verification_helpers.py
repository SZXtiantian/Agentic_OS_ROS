from __future__ import annotations

from agentic_runtime.verification.scheduler_capability import (
    backend_step_hints,
    backend_next_steps,
    bridge_missing_evidence,
    dependency_next_action,
    failure_reason,
    live_ros_graph_evidence,
    profile_dependency_evidence,
    sanitize_reason,
    summarize_cli_stderr,
)


def test_scheduler_capability_next_action_includes_bridge_readiness_evidence():
    decision = {
        "error_code": "ROS_BRIDGE_UNAVAILABLE",
        "syscall_id": "ksc_verify_capability",
    }
    recent_syscalls = [
        {
            "syscall_id": "ksc_verify_capability",
            "audit_id": "audit_verify_capability",
        }
    ]
    recent_audit_records = [
        {
            "audit_id": "audit_verify_capability",
            "error_code": "ROS_BRIDGE_UNAVAILABLE",
            "result": {
                "data": {
                    "reason": "  no real camera, arm, or gripper bridge backend is visible  ",
                    "state": {
                        "state": {
                            "camera_ready": False,
                            "camera_topics": ["/depth_cam/rgb0/image_raw", "/camera/color/image_raw"],
                            "arm_backend_available": False,
                            "arm_backend_type": "servo_action_group",
                            "arm_command_topic": "/servo_controller",
                            "gripper_topic_visible": False,
                            "gripper_topic": "/servo_controller",
                            "action_files_available": {
                                "DeliverCup": True,
                                "PickCup": False,
                            },
                        }
                    },
                }
            },
        }
    ]

    next_action = dependency_next_action(
        "ROS_BRIDGE_UNAVAILABLE",
        decision,
        recent_syscalls,
        recent_audit_records,
        live_ros_graph={
            "nodes": ["/state_bridge_node"],
            "topics": ["/rosout", "/parameter_events"],
            "services": ["/agentic/robot/get_state"],
            "actions": [],
        },
    )

    assert next_action.startswith("configure and verify the real bridge/backend")
    assert "bridge_reason=no real camera, arm, or gripper bridge backend is visible" in next_action
    assert "bridge_missing=" in next_action
    assert "camera_topics=/depth_cam/rgb0/image_raw,/camera/color/image_raw" in next_action
    assert "arm_backend=servo_action_group:/servo_controller" in next_action
    assert "gripper_topic=/servo_controller" in next_action
    assert "action_files=PickCup" in next_action
    assert "ros_graph=" in next_action
    assert "nodes=1" in next_action
    assert "state_bridge_node=visible" in next_action
    assert "camera_candidate_visible=none" in next_action
    assert "arm_topic_visible=/servo_controller:false" in next_action


def test_scheduler_capability_bridge_missing_evidence_uses_matching_error_code_only():
    recent_audit_records = [
        {
            "error_code": "OTHER_ERROR",
            "result": {
                "data": {
                    "state": {
                        "state": {
                            "camera_ready": False,
                            "camera_topics": ["/unrelated"],
                        }
                    }
                }
            },
        },
        {
            "error_code": "ROS_BRIDGE_UNAVAILABLE",
            "result": {
                "data": {
                    "state": {
                        "state": {
                            "camera_ready": False,
                            "camera_topics": ["/camera/color/image_raw"],
                        }
                    }
                }
            },
        },
    ]

    assert bridge_missing_evidence("ROS_BRIDGE_UNAVAILABLE", recent_audit_records) == (
        "camera_topics=/camera/color/image_raw"
    )


def test_scheduler_capability_live_ros_graph_evidence_summarizes_candidate_visibility():
    readiness = {
        "camera_topics": ["/depth_cam/rgb0/image_raw", "/camera/color/image_raw"],
        "arm_command_topic": "/servo_controller",
        "gripper_topic": "/servo_controller",
    }
    graph = {
        "nodes": ["/state_bridge_node", "/camera_driver"],
        "topics": ["/rosout", "/depth_cam/rgb0/image_raw", "/parameter_events"],
        "services": ["/agentic/robot/get_state"],
        "actions": ["/inspect_area"],
    }

    evidence = live_ros_graph_evidence(readiness, graph)

    assert "nodes=2" in evidence
    assert "topics=3" in evidence
    assert "services=1" in evidence
    assert "actions=1" in evidence
    assert "state_bridge_node=visible" in evidence
    assert "camera_candidate_visible=/depth_cam/rgb0/image_raw" in evidence
    assert "arm_topic_visible=/servo_controller:false" in evidence
    assert "gripper_topic_visible=/servo_controller:false" in evidence


def test_scheduler_capability_live_ros_graph_evidence_reports_empty_backend_graph_counts():
    evidence = live_ros_graph_evidence(
        {},
        {
            "nodes": [],
            "topics": ["/parameter_events", "/rosout"],
            "services": [],
            "actions": [],
        },
    )

    assert "nodes=0" in evidence
    assert "topics=2" in evidence
    assert "services=0" in evidence
    assert "actions=0" in evidence
    assert "state_bridge_node=not_visible" in evidence


def test_scheduler_capability_profile_dependency_evidence_summarizes_launch_and_visibility(tmp_path):
    present_action = tmp_path / "init.d6a"
    present_action.write_text("real action group bytes", encoding="utf-8")
    missing_action = tmp_path / "horizontal.d6a"
    present_launch = tmp_path / "depth_camera.launch.py"
    present_launch.write_text("real launch file", encoding="utf-8")
    missing_launch = tmp_path / "usb_cam.launch.py"
    profile = {
        "camera": {
            "primary_rgb_topic": "/depth_cam/rgb0/image_raw",
            "fallback_rgb_topics": ["/camera/color/image_raw"],
            "depth_topics": ["/depth_cam/depth0/image_raw"],
            "point_cloud_topics": ["/depth_cam/depth0/points"],
        },
        "gripper": {
            "servo_command_topic": "/servo_controller",
        },
        "discovered_interfaces": {
            "camera_launch": [
                str(present_launch),
                str(missing_launch),
            ],
            "candidate_camera_topics": ["/depth_cam/rgb0/image_raw", "/camera/color/image_raw"],
            "arm_topics": ["/servo_controller", "/joint_controller"],
            "arm_services": ["/kinematics/set_pose_target"],
            "action_group_files": [str(present_action), str(missing_action)],
            "optional_vendor_nodes_not_running_in_current_graph": ["/claw_arm_group_control"],
        },
    }
    graph = {
        "topics": ["/depth_cam/rgb0/image_raw", "/servo_controller"],
        "services": [],
    }

    evidence = profile_dependency_evidence(profile, graph)

    assert "camera_backend=topic_visible" in evidence
    assert "arm_backend=graph_visible" in evidence
    assert "gripper_backend=topic_visible" in evidence
    assert "camera_launch_files_present=1/2" in evidence
    assert "first_camera_launch=depth_camera.launch.py" in evidence
    assert "camera_topics_visible=1/4" in evidence
    assert "action_group_files_present=1/2" in evidence


def test_scheduler_capability_profile_dependency_evidence_classifies_absent_backends(tmp_path):
    launch_file = tmp_path / "depth_camera.launch.py"
    launch_file.write_text("real launch file", encoding="utf-8")
    action_file = tmp_path / "init.d6a"
    action_file.write_text("real action group bytes", encoding="utf-8")
    profile = {
        "camera": {"primary_rgb_topic": "/depth_cam/rgb0/image_raw"},
        "gripper": {"servo_command_topic": "/servo_controller"},
        "discovered_interfaces": {
            "camera_launch": [str(launch_file)],
            "arm_topics": ["/servo_controller"],
            "arm_services": ["/kinematics/set_pose_target"],
            "action_group_files": [str(action_file)],
        },
    }

    evidence = profile_dependency_evidence(profile, {"topics": [], "services": []})

    assert "camera_backend=launch_present_topic_absent" in evidence
    assert "arm_backend=artifacts_present_graph_absent" in evidence
    assert "gripper_backend=topic_absent" in evidence


def test_scheduler_capability_backend_next_steps_use_profile_artifact_evidence(tmp_path):
    launch_file = tmp_path / "depth_camera.launch.py"
    launch_file.write_text("real launch file", encoding="utf-8")
    action_file = tmp_path / "init.d6a"
    action_file.write_text("real action group bytes", encoding="utf-8")
    profile = {
        "camera": {"primary_rgb_topic": "/depth_cam/rgb0/image_raw"},
        "gripper": {"servo_command_topic": "/servo_controller"},
        "discovered_interfaces": {
            "camera_launch": [str(launch_file)],
            "arm_topics": ["/servo_controller"],
            "arm_services": ["/kinematics/set_pose_target"],
            "action_group_files": [str(action_file)],
        },
    }

    steps = backend_next_steps(
        "ROS_SERVICE_UNAVAILABLE",
        {},
        {"nodes": [], "topics": ["/rosout"], "services": []},
        profile,
    )

    assert steps == [
        "start_agentic_state_bridge",
        "start_camera_launch",
        "start_arm_servo_controller",
    ]


def test_scheduler_capability_backend_next_steps_preserve_bridge_visible_backend_gap(tmp_path):
    launch_file = tmp_path / "depth_camera.launch.py"
    launch_file.write_text("real launch file", encoding="utf-8")
    action_file = tmp_path / "init.d6a"
    action_file.write_text("real action group bytes", encoding="utf-8")
    profile = {
        "camera": {"primary_rgb_topic": "/depth_cam/rgb0/image_raw"},
        "gripper": {"servo_command_topic": "/servo_controller"},
        "discovered_interfaces": {
            "camera_launch": [str(launch_file)],
            "arm_topics": ["/servo_controller"],
            "action_group_files": [str(action_file)],
        },
    }
    readiness = {
        "camera_ready": False,
        "arm_backend_available": False,
        "gripper_topic_visible": False,
    }

    steps = backend_next_steps(
        "ROS_BRIDGE_UNAVAILABLE",
        readiness,
        {"nodes": ["/state_bridge_node"], "topics": ["/rosout"], "services": ["/agentic/robot/get_state"]},
        profile,
    )

    assert steps == ["start_camera_launch", "start_arm_servo_controller"]


def test_scheduler_capability_backend_step_hints_are_non_executing_operator_guidance(tmp_path):
    launch_file = tmp_path / "depth_camera.launch.py"
    launch_file.write_text("real launch file", encoding="utf-8")
    profile = {
        "discovered_interfaces": {
            "camera_launch": [str(launch_file)],
        },
    }

    hints = backend_step_hints(
        [
            "start_agentic_state_bridge",
            "start_camera_launch",
            "start_arm_servo_controller",
            "start_gripper_servo_topic",
        ],
        profile,
    )

    assert hints == [
        "start_agentic_state_bridge=use_opt_in_readonly_state_bridge_or_start_command",
        "start_camera_launch=start_profile_camera_launch:first_camera_launch=depth_camera.launch.py",
        "start_arm_servo_controller=operator_gated_real_arm_startup",
        "start_gripper_servo_topic=operator_gated_real_gripper_startup",
    ]


def test_scheduler_capability_failure_reason_prefers_matching_syscall_audit_record():
    decision = {
        "error_code": "ROS_BRIDGE_UNAVAILABLE",
        "syscall_id": "ksc_selected",
    }
    recent_syscalls = [
        {"syscall_id": "ksc_other", "audit_id": "audit_other", "reason": "unrelated"},
        {"syscall_id": "ksc_selected", "audit_id": "audit_selected"},
    ]
    recent_audit_records = [
        {
            "audit_id": "audit_other",
            "error_code": "ROS_BRIDGE_UNAVAILABLE",
            "reason": "older unrelated reason",
        },
        {
            "audit_id": "audit_selected",
            "error_code": "ROS_BRIDGE_UNAVAILABLE",
            "result": {"reason": "selected audit explains the bridge failure"},
        },
    ]

    assert failure_reason(decision, recent_syscalls, recent_audit_records) == (
        "selected audit explains the bridge failure"
    )


def test_scheduler_capability_next_action_redacts_sensitive_reason_text():
    next_action = dependency_next_action(
        "ROS_BRIDGE_UNAVAILABLE",
        {
            "error_code": "ROS_BRIDGE_UNAVAILABLE",
            "syscall_id": "ksc_sensitive",
            "reason": "api_key=secret-value prompt=private user instruction token=abc123 bridge offline",
        },
        [],
        [],
    )

    assert "secret-value" not in next_action
    assert "private user instruction" not in next_action
    assert "abc123" not in next_action
    assert "api_key=[REDACTED]" in next_action
    assert "prompt=[REDACTED]" in next_action
    assert "token=[REDACTED]" in next_action


def test_scheduler_capability_reason_redacts_openai_style_secret():
    assert sanitize_reason("provider returned sk-liveSECRET123456789 unavailable") == (
        "provider returned sk-[REDACTED] unavailable"
    )


def test_scheduler_capability_cli_stderr_summary_does_not_emit_raw_traceback_or_secret():
    stderr = "\n".join(
        [
            "Traceback (most recent call last):",
            '  File "/opt/ros/humble/bin/ros2", line 33, in <module>',
            "RuntimeError: api_key=secret-value prompt=private bridge trace",
        ]
    )

    summary = summarize_cli_stderr(stderr)

    assert "stderr_sha256=" in summary
    assert "stderr_length=" in summary
    assert "stderr_first_line=Traceback" in summary
    assert "/opt/ros/humble/bin/ros2" not in summary
    assert "secret-value" not in summary
    assert "private bridge trace" not in summary


def test_scheduler_capability_cli_stderr_summary_keeps_short_non_sensitive_error():
    assert summarize_cli_stderr("daemon unavailable") == "stderr=daemon unavailable"
