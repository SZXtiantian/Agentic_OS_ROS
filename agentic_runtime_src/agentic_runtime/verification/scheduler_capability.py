from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


_SENSITIVE_KEY_PATTERN = r"(?:api[_-]?key|apikey|secret|token|password|prompt|content|messages)"
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    rf"\b({_SENSITIVE_KEY_PATTERN})\b\s*[:=]\s*(?:(?!\s+\b{_SENSITIVE_KEY_PATTERN}\b\s*[:=]).)+",
    re.IGNORECASE,
)
_OPENAI_STYLE_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def dependency_next_action(
    error_code: str,
    decision: dict[str, Any],
    recent_syscalls: list[dict[str, Any]],
    recent_audit_records: list[dict[str, Any]],
    live_ros_graph: dict[str, Any] | None = None,
    bridge_profile: dict[str, Any] | None = None,
) -> str:
    base = "configure and verify the real bridge/backend for the selected capability"
    reason = failure_reason(decision, recent_syscalls, recent_audit_records)
    readiness = bridge_readiness_payload(error_code, recent_audit_records)
    missing = bridge_missing_evidence(error_code, recent_audit_records)
    graph = live_ros_graph_evidence(readiness, live_ros_graph or {})
    profile = profile_dependency_evidence(bridge_profile or {}, live_ros_graph or {})
    steps = backend_next_steps(error_code, readiness, live_ros_graph or {}, bridge_profile or {})
    parts = [base]
    if reason:
        parts.append(f"bridge_reason={reason}")
    if missing:
        parts.append(f"bridge_missing={missing}")
    if steps:
        parts.append(f"next_backend_steps={','.join(steps)}")
        hints = backend_step_hints(steps, bridge_profile or {})
        if hints:
            parts.append(f"backend_step_hints={','.join(hints)}")
    if graph:
        parts.append(f"ros_graph={graph}")
    if profile:
        parts.append(f"profile_dependencies={profile}")
    return "; ".join(parts)


def backend_next_steps(
    error_code: str,
    readiness: dict[str, Any],
    live_ros_graph: dict[str, Any],
    bridge_profile: dict[str, Any],
) -> list[str]:
    topics = _string_set(live_ros_graph.get("topics"))
    nodes = _string_set(live_ros_graph.get("nodes"))
    services = _string_set(live_ros_graph.get("services"))
    state_bridge_visible = any(name.rstrip("/").endswith("state_bridge_node") for name in nodes)
    steps: list[str] = []
    if error_code == "ROS_SERVICE_UNAVAILABLE" and not state_bridge_visible:
        steps.append("start_agentic_state_bridge")
    profile = bridge_profile if isinstance(bridge_profile, dict) else {}
    discovered = profile.get("discovered_interfaces")
    if not isinstance(discovered, dict):
        discovered = {}
    camera_topics = _unique_strings(
        [
            *camera_launch_topics(profile),
            *_string_list(discovered.get("candidate_camera_topics")),
        ]
    )
    camera_launch = _string_list(discovered.get("camera_launch"))
    if camera_topics and not any(topic in topics for topic in camera_topics):
        if camera_launch and all(Path(path).exists() for path in camera_launch):
            steps.append("start_camera_launch")
        elif camera_launch:
            steps.append("install_camera_launch")
        else:
            steps.append("configure_camera_backend")
    arm_topics = _string_list(discovered.get("arm_topics"))
    arm_services = _string_list(discovered.get("arm_services"))
    arm_visible = any(topic in topics for topic in arm_topics) or any(service in services for service in arm_services)
    action_group_files = _string_list(discovered.get("action_group_files"))
    if (arm_topics or arm_services) and not arm_visible:
        if action_group_files and all(Path(path).exists() for path in action_group_files):
            steps.append("start_arm_servo_controller")
        elif action_group_files:
            steps.append("install_action_group_files")
        else:
            steps.append("configure_arm_backend")
    gripper_topic = _gripper_topic(profile)
    if gripper_topic and gripper_topic not in topics and "start_arm_servo_controller" not in steps:
        steps.append("start_gripper_servo_topic")
    if readiness.get("camera_ready") is False and "start_camera_launch" not in steps and "install_camera_launch" not in steps:
        steps.append("verify_camera_backend")
    if readiness.get("arm_backend_available") is False and "start_arm_servo_controller" not in steps and "install_action_group_files" not in steps:
        steps.append("verify_arm_backend")
    if readiness.get("gripper_topic_visible") is False and "start_gripper_servo_topic" not in steps and "start_arm_servo_controller" not in steps:
        steps.append("verify_gripper_backend")
    return _unique_strings(steps)


def backend_step_hints(steps: list[str], bridge_profile: dict[str, Any]) -> list[str]:
    profile = bridge_profile if isinstance(bridge_profile, dict) else {}
    discovered = profile.get("discovered_interfaces")
    if not isinstance(discovered, dict):
        discovered = {}
    camera_launch = _string_list(discovered.get("camera_launch"))
    first_camera_launch = Path(camera_launch[0]).name if camera_launch else ""
    hints: list[str] = []
    for step in steps:
        if step == "start_agentic_state_bridge":
            hints.append("start_agentic_state_bridge=use_opt_in_readonly_state_bridge_or_start_command")
        elif step == "start_camera_launch":
            detail = f":first_camera_launch={first_camera_launch}" if first_camera_launch else ""
            hints.append(f"start_camera_launch=start_profile_camera_launch{detail}")
        elif step == "install_camera_launch":
            hints.append("install_camera_launch=restore_profile_camera_launch_files")
        elif step == "configure_camera_backend":
            hints.append("configure_camera_backend=declare_real_camera_topics_in_profile")
        elif step == "start_arm_servo_controller":
            hints.append("start_arm_servo_controller=operator_gated_real_arm_startup")
        elif step == "install_action_group_files":
            hints.append("install_action_group_files=restore_real_action_group_artifacts")
        elif step == "configure_arm_backend":
            hints.append("configure_arm_backend=declare_real_arm_topics_or_services")
        elif step == "start_gripper_servo_topic":
            hints.append("start_gripper_servo_topic=operator_gated_real_gripper_startup")
        elif step == "verify_camera_backend":
            hints.append("verify_camera_backend=check_real_camera_topics")
        elif step == "verify_arm_backend":
            hints.append("verify_arm_backend=check_real_arm_graph")
        elif step == "verify_gripper_backend":
            hints.append("verify_gripper_backend=check_real_gripper_topic")
    return _unique_strings(hints)


def failure_reason(
    decision: dict[str, Any],
    recent_syscalls: list[dict[str, Any]],
    recent_audit_records: list[dict[str, Any]],
) -> str:
    syscall_id = str(decision.get("syscall_id") or "")
    syscall_record = next(
        (item for item in reversed(recent_syscalls) if item.get("syscall_id") == syscall_id),
        {},
    )
    audit_id = str(syscall_record.get("audit_id") or "")
    audit_record = next(
        (record for record in reversed(recent_audit_records) if record.get("audit_id") == audit_id),
        {},
    )
    candidates = [
        decision.get("reason"),
        syscall_record.get("reason"),
        audit_record.get("reason"),
    ]
    result = audit_record.get("result")
    if isinstance(result, dict):
        data = result.get("data")
        candidates.extend(
            [
                result.get("reason"),
                data.get("reason") if isinstance(data, dict) else "",
            ]
        )
    for candidate in candidates:
        reason = sanitize_reason(candidate)
        if reason:
            return reason
    error_code = str(decision.get("error_code") or "")
    for record in reversed(recent_audit_records):
        if error_code and record.get("error_code") != error_code:
            continue
        result = record.get("result")
        if not isinstance(result, dict):
            continue
        data = result.get("data")
        for candidate in (
            result.get("reason"),
            data.get("reason") if isinstance(data, dict) else "",
        ):
            reason = sanitize_reason(candidate)
            if reason:
                return reason
    return ""


def bridge_missing_evidence(error_code: str, recent_audit_records: list[dict[str, Any]]) -> str:
    readiness = bridge_readiness_payload(error_code, recent_audit_records)
    if not readiness:
        return ""
    missing: list[str] = []
    if readiness.get("camera_ready") is False:
        camera_topics = ",".join(str(item) for item in list(readiness.get("camera_topics") or []) if item)
        missing.append(f"camera_topics={camera_topics or 'unreported'}")
    if readiness.get("arm_backend_available") is False:
        arm_topic = str(readiness.get("arm_command_topic") or "")
        arm_service = str(readiness.get("arm_status_service") or "")
        arm_backend = str(readiness.get("arm_backend_type") or "")
        missing.append(f"arm_backend={arm_backend or 'unreported'}:{arm_topic or arm_service or 'unreported'}")
    if readiness.get("gripper_topic_visible") is False:
        missing.append(f"gripper_topic={readiness.get('gripper_topic') or 'unreported'}")
    action_files = readiness.get("action_files_available")
    if isinstance(action_files, dict):
        missing_actions = [str(name) for name, available in sorted(action_files.items()) if available is False]
        if missing_actions:
            missing.append("action_files=" + ",".join(missing_actions))
    return sanitize_reason("; ".join(item for item in missing if item))


def bridge_readiness_payload(error_code: str, recent_audit_records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in reversed(recent_audit_records):
        if error_code and record.get("error_code") != error_code:
            continue
        result = record.get("result")
        if not isinstance(result, dict):
            continue
        data = result.get("data")
        if not isinstance(data, dict):
            continue
        state = data.get("state")
        if not isinstance(state, dict):
            continue
        readiness = state.get("state")
        if isinstance(readiness, dict):
            return readiness
    return {}


def live_ros_graph_evidence(readiness: dict[str, Any], live_ros_graph: dict[str, Any]) -> str:
    if not live_ros_graph:
        return ""
    nodes = _string_set(live_ros_graph.get("nodes"))
    topics = _string_set(live_ros_graph.get("topics"))
    services = _string_set(live_ros_graph.get("services"))
    actions = _string_set(live_ros_graph.get("actions"))
    camera_candidates = [str(item) for item in list(readiness.get("camera_topics") or []) if item]
    camera_visible = [topic for topic in camera_candidates if topic in topics]
    arm_topic = str(readiness.get("arm_command_topic") or "")
    gripper_topic = str(readiness.get("gripper_topic") or "")
    state_bridge_visible = any(name.rstrip("/").endswith("state_bridge_node") for name in nodes)
    parts = [
        f"nodes={len(nodes)}",
        f"topics={len(topics)}",
        f"services={len(services)}",
        f"actions={len(actions)}",
        f"state_bridge_node={'visible' if state_bridge_visible else 'not_visible'}",
    ]
    if camera_candidates:
        parts.append(f"camera_candidate_visible={','.join(camera_visible) if camera_visible else 'none'}")
    if arm_topic:
        parts.append(f"arm_topic_visible={arm_topic}:{str(arm_topic in topics).lower()}")
    if gripper_topic:
        parts.append(f"gripper_topic_visible={gripper_topic}:{str(gripper_topic in topics).lower()}")
    errors = _string_list(live_ros_graph.get("errors"))
    if errors:
        parts.append(f"query_errors={','.join(errors[:2])}")
    return sanitize_reason("; ".join(parts))


def profile_dependency_evidence(profile: dict[str, Any], live_ros_graph: dict[str, Any]) -> str:
    if not isinstance(profile, dict) or not profile:
        return ""
    discovered = profile.get("discovered_interfaces")
    if not isinstance(discovered, dict):
        discovered = {}
    topics = _string_set(live_ros_graph.get("topics"))
    services = _string_set(live_ros_graph.get("services"))
    camera_launch = _string_list(discovered.get("camera_launch"))
    camera_topics = _unique_strings(
        [
            *camera_launch_topics(profile),
            *_string_list(discovered.get("candidate_camera_topics")),
        ]
    )
    arm_topics = _string_list(discovered.get("arm_topics"))
    arm_services = _string_list(discovered.get("arm_services"))
    action_group_files = _string_list(discovered.get("action_group_files"))
    gripper_topic = _gripper_topic(profile)
    visible_camera_topics = [topic for topic in camera_topics if topic in topics]
    visible_arm_topics = [topic for topic in arm_topics if topic in topics]
    visible_arm_services = [service for service in arm_services if service in services]
    present_launches = [path for path in camera_launch if Path(path).exists()]
    present_action_files = [path for path in action_group_files if Path(path).exists()]
    parts: list[str] = []
    camera_backend = _camera_backend_status(
        camera_topics=camera_topics,
        visible_camera_topics=visible_camera_topics,
        camera_launch=camera_launch,
        present_launches=present_launches,
    )
    if camera_backend:
        parts.append(f"camera_backend={camera_backend}")
    arm_backend = _arm_backend_status(
        arm_topics=arm_topics,
        arm_services=arm_services,
        visible_arm_topics=visible_arm_topics,
        visible_arm_services=visible_arm_services,
        action_group_files=action_group_files,
        present_action_files=present_action_files,
    )
    if arm_backend:
        parts.append(f"arm_backend={arm_backend}")
    if gripper_topic:
        parts.append(f"gripper_backend={'topic_visible' if gripper_topic in topics else 'topic_absent'}")
    if action_group_files:
        parts.append(f"action_group_files_present={len(present_action_files)}/{len(action_group_files)}")
    if camera_launch:
        parts.append(f"camera_launch_files_present={len(present_launches)}/{len(camera_launch)}")
        parts.append(f"first_camera_launch={Path(camera_launch[0]).name}")
    if camera_topics:
        parts.append(f"camera_topics_visible={len(visible_camera_topics)}/{len(camera_topics)}")
    if arm_topics:
        parts.append(f"arm_topics_visible={len(visible_arm_topics)}/{len(arm_topics)}")
    if arm_services:
        parts.append(f"arm_services_visible={len(visible_arm_services)}/{len(arm_services)}")
    optional_nodes = _string_list(discovered.get("optional_vendor_nodes_not_running_in_current_graph"))
    if optional_nodes:
        parts.append("optional_vendor_nodes=" + ",".join(optional_nodes[:3]))
    return sanitize_reason("; ".join(parts))


def _camera_backend_status(
    *,
    camera_topics: list[str],
    visible_camera_topics: list[str],
    camera_launch: list[str],
    present_launches: list[str],
) -> str:
    if not camera_topics:
        return ""
    if visible_camera_topics:
        return "topic_visible"
    if camera_launch and len(present_launches) == len(camera_launch):
        return "launch_present_topic_absent"
    if present_launches:
        return "partial_launch_present_topic_absent"
    if camera_launch:
        return "launch_missing_topic_absent"
    return "topic_absent"


def _arm_backend_status(
    *,
    arm_topics: list[str],
    arm_services: list[str],
    visible_arm_topics: list[str],
    visible_arm_services: list[str],
    action_group_files: list[str],
    present_action_files: list[str],
) -> str:
    if not arm_topics and not arm_services:
        return ""
    if visible_arm_topics or visible_arm_services:
        return "graph_visible"
    if action_group_files and len(present_action_files) == len(action_group_files):
        return "artifacts_present_graph_absent"
    if present_action_files:
        return "partial_artifacts_present_graph_absent"
    if action_group_files:
        return "artifacts_missing_graph_absent"
    return "graph_absent"


def _gripper_topic(profile: dict[str, Any]) -> str:
    gripper = profile.get("gripper")
    if not isinstance(gripper, dict):
        return ""
    return str(gripper.get("servo_command_topic") or "")


def camera_launch_topics(profile: dict[str, Any]) -> list[str]:
    camera = profile.get("camera")
    if not isinstance(camera, dict):
        return []
    return _unique_strings(
        [
            str(camera.get("primary_rgb_topic") or ""),
            *_string_list(camera.get("fallback_rgb_topics")),
            *_string_list(camera.get("depth_topics")),
            *_string_list(camera.get("point_cloud_topics")),
        ]
    )


def _string_set(value: Any) -> set[str]:
    return set(_string_list(value))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result


def sanitize_reason(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    reason = " ".join(value.split())
    if not reason:
        return ""
    reason = _SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", reason)
    reason = _OPENAI_STYLE_SECRET_RE.sub("sk-[REDACTED]", reason)
    return reason[:240]


def summarize_cli_stderr(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if not stripped:
        return "stderr=empty"
    sanitized = sanitize_reason(stripped)
    if "Traceback" not in stripped and len(sanitized) <= 160:
        return f"stderr={sanitized}"
    first_line = sanitize_reason(stripped.splitlines()[0])
    digest = hashlib.sha256(stripped.encode("utf-8", errors="replace")).hexdigest()
    return f"stderr_sha256={digest}; stderr_length={len(stripped)}; stderr_first_line={first_line[:80]}"
