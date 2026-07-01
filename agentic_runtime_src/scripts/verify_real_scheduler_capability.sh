#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source_if_exists() {
  local setup_file="$1"
  if [ -f "$setup_file" ]; then
    set +u
    # shellcheck disable=SC1090
    . "$setup_file"
    set -u
  fi
}

source_if_exists "${AGENTIC_ROS2_SETUP:-/opt/ros/humble/setup.bash}"
source_if_exists "${AGENTIC_ROS2_BRIDGE_SETUP:-/home/ubuntu/agentic_ws/install/setup.bash}"

echo "CHECK_NAME=real_scheduler_capability"
echo "REQUIRED_ENV=AGENTIC_VERIFY_REAL_SCHEDULER_CAPABILITY=1"

if [ "${AGENTIC_VERIFY_REAL_SCHEDULER_CAPABILITY:-0}" != "1" ]; then
  echo "RESULT=UNVERIFIED_REAL_DEPENDENCY"
  echo "ERROR_CODE=UNVERIFIED_REAL_DEPENDENCY"
  echo "NEXT_ACTION=set AGENTIC_VERIFY_REAL_SCHEDULER_CAPABILITY=1 with real bridge/capability configuration"
  exit 2
fi

export AGENTIC_RUNTIME_CONFIG="${AGENTIC_RUNTIME_CONFIG:-$PWD/configs/runtime.yaml}"
export AGENTIC_VAR="${AGENTIC_VAR:-$PWD/var/verify_scheduler_capability}"
export AGENTIC_VERIFY_BRIDGE_PROFILE_FILE="${AGENTIC_VERIFY_BRIDGE_PROFILE_FILE:-/opt/agentic/etc/robot_profiles/rosorin_arm_camera.yaml}"

AUTO_STARTED_STATE_BRIDGE_PID=""

cleanup_readonly_state_bridge() {
  if [ -n "$AUTO_STARTED_STATE_BRIDGE_PID" ]; then
    kill "$AUTO_STARTED_STATE_BRIDGE_PID" 2>/dev/null || true
    wait "$AUTO_STARTED_STATE_BRIDGE_PID" 2>/dev/null || true
  fi
}

trap cleanup_readonly_state_bridge EXIT

start_readonly_state_bridge_if_requested() {
  if [ "${AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE:-0}" != "1" ]; then
    return
  fi
  export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS="requested"
  if ! command -v ros2 >/dev/null 2>&1; then
    export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS="ros2_unavailable"
    return
  fi
  local log_path="${AGENTIC_VERIFY_STATE_BRIDGE_LOG:-$AGENTIC_VAR/state_bridge_node.log}"
  mkdir -p "$(dirname "$log_path")"
  ros2 run agentic_capability_bridge state_bridge_node --ros-args \
    -p "bridge_profile_file:=$AGENTIC_VERIFY_BRIDGE_PROFILE_FILE" >"$log_path" 2>&1 &
  AUTO_STARTED_STATE_BRIDGE_PID="$!"
  export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS="attempted"
  export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_PID="$AUTO_STARTED_STATE_BRIDGE_PID"
  export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_LOG="$log_path"
  sleep "${AGENTIC_VERIFY_STATE_BRIDGE_STARTUP_WAIT:-3}"
  if kill -0 "$AUTO_STARTED_STATE_BRIDGE_PID" 2>/dev/null; then
    export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS="running"
  else
    export AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS="exited"
  fi
}

start_readonly_state_bridge_if_requested

PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, ResourceRequest, TaskGraph, TaskNode
from agentic_runtime.server import RuntimeServer
from agentic_runtime.verification.scheduler_capability import backend_next_steps, backend_step_hints, dependency_next_action, live_ros_graph_evidence, profile_dependency_evidence, sanitize_reason, summarize_cli_stderr


def unverified(error_code: str, next_action: str) -> int:
    print("RESULT=UNVERIFIED_REAL_DEPENDENCY")
    print(f"ERROR_CODE={error_code}")
    print(f"NEXT_ACTION={next_action}")
    return 2


def fail(error_code: str, next_action: str) -> int:
    print("RESULT=FAIL")
    print(f"ERROR_CODE={error_code}")
    print(f"NEXT_ACTION={next_action}")
    return 1


def preflight_ros_interface(capability_spec) -> tuple[str, str]:
    ros2 = getattr(capability_spec, "ros2", None)
    if ros2 is None or not getattr(ros2, "name", ""):
        return "", ""
    if shutil.which("ros2") is None:
        return "ROS_BRIDGE_UNAVAILABLE", "install/source ROS2 so the ros2 CLI is available"
    interface_kind = str(getattr(ros2, "kind", "") or "").lower()
    interface_name = str(getattr(ros2, "name", "") or "")
    if interface_kind == "service":
        return _preflight_ros2_list(
            ["ros2", "service", "list"],
            interface_name,
            "ROS_SERVICE_UNAVAILABLE",
            "service",
        )
    if interface_kind == "action":
        return _preflight_ros2_list(
            ["ros2", "action", "list"],
            interface_name,
            "ROS_ACTION_UNAVAILABLE",
            "action",
        )
    return "", ""


def _preflight_ros2_list(command: list[str], required_name: str, error_code: str, interface_kind: str) -> tuple[str, str]:
    attempts = _ros_discovery_attempts()
    delay_s = _ros_discovery_retry_delay_s()
    available: set[str] = set()
    for attempt in range(attempts):
        try:
            result = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=8,
                check=False,
            )
        except FileNotFoundError:
            return "ROS_BRIDGE_UNAVAILABLE", "install/source ROS2 so the ros2 CLI is available"
        except subprocess.TimeoutExpired:
            return error_code, f"ROS2 graph query timed out while looking for {interface_kind} {required_name}; command={' '.join(command)}"
        if result.returncode != 0:
            return "ROS_BRIDGE_UNAVAILABLE", f"fix ROS2 graph query {' '.join(command)}; {summarize_cli_stderr(result.stderr)}"
        available = {line.strip().split(" ", 1)[0] for line in result.stdout.splitlines() if line.strip()}
        if required_name in available:
            return "", ""
        if attempt + 1 < attempts:
            time.sleep(delay_s)
    return error_code, _missing_ros_interface_next_action(
        interface_kind=interface_kind,
        required_name=required_name,
        visible_count=len(available),
        command=command,
        discovery_attempts=attempts,
    )


def _missing_ros_interface_next_action(*, interface_kind: str, required_name: str, visible_count: int, command: list[str], discovery_attempts: int = 1) -> str:
    plural = "services" if interface_kind == "service" else "actions"
    start_hint = _ros_interface_start_hint(interface_kind=interface_kind, required_name=required_name)
    executable_hints = _ros_interface_executable_hints(interface_kind=interface_kind, required_name=required_name)
    parts = [
        f"start the real bridge {interface_kind} {required_name}; "
        f"required={required_name}; "
        f"visible_{plural}={visible_count}; "
        f"command={' '.join(command)}"
    ]
    if discovery_attempts > 1:
        parts.append(f"discovery_attempts={discovery_attempts}")
    if start_hint:
        parts.append(f"start_command={start_hint}")
    parts.extend(executable_hints)
    live_graph = _ros_graph_snapshot()
    steps = backend_next_steps(
        "ROS_SERVICE_UNAVAILABLE" if interface_kind == "service" else "ROS_ACTION_UNAVAILABLE",
        {},
        live_graph,
        _load_bridge_profile(),
    )
    if steps:
        parts.append(f"next_backend_steps={','.join(steps)}")
        hints = backend_step_hints(steps, _load_bridge_profile())
        if hints:
            parts.append(f"backend_step_hints={','.join(hints)}")
    graph_hint = live_ros_graph_evidence({}, live_graph)
    if graph_hint:
        parts.append(f"ros_graph={graph_hint}")
    profile_hint = _bridge_profile_dependency_hint(live_graph)
    if profile_hint:
        parts.append(profile_hint)
    auto_start_hint = _readonly_state_bridge_auto_start_hint()
    if auto_start_hint:
        parts.append(auto_start_hint)
    return "; ".join(parts)


def _ros_discovery_attempts() -> int:
    try:
        return max(1, int(os.environ.get("AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS", "4")))
    except ValueError:
        return 4


def _ros_discovery_retry_delay_s() -> float:
    try:
        return max(0.1, float(os.environ.get("AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S", "1.0")))
    except ValueError:
        return 1.0


def _ros_interface_start_hint(*, interface_kind: str, required_name: str) -> str:
    if interface_kind == "service" and required_name == "/agentic/robot/get_state":
        return "ros2 run agentic_capability_bridge state_bridge_node"
    return ""


def _ros_interface_executable_hints(*, interface_kind: str, required_name: str) -> list[str]:
    if interface_kind == "service" and required_name == "/agentic/robot/get_state":
        package = "agentic_capability_bridge"
        executable = "state_bridge_node"
        status, error = _ros_package_executable_status(package, executable)
        hints = [
            f"bridge_executable={package}/{executable}:{status}",
            f"executable_command=ros2 pkg executables {package}",
        ]
        if error:
            hints.append(f"executable_error={error}")
        return hints
    return []


def _ros_package_executable_status(package: str, executable: str) -> tuple[str, str]:
    command = ["ros2", "pkg", "executables", package]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return "query_failed", "ros2 CLI unavailable"
    except subprocess.TimeoutExpired:
        return "query_timeout", ""
    if result.returncode != 0:
        return "query_failed", summarize_cli_stderr(result.stderr)
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0] == package and fields[1] == executable:
            return "available", ""
    return "missing", ""


def _readonly_state_bridge_auto_start_hint() -> str:
    if os.environ.get("AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE") != "1":
        return ""
    status = sanitize_reason(os.environ.get("AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS") or "requested")
    log_path = sanitize_reason(os.environ.get("AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_LOG") or "")
    parts = [f"auto_start_readonly_state_bridge={status or 'requested'}"]
    if log_path:
        parts.append(f"auto_start_log={log_path}")
    return "; ".join(parts)


def _bridge_profile_dependency_hint(live_ros_graph: dict[str, list[str]]) -> str:
    profile = _load_bridge_profile()
    if not profile:
        return ""
    evidence = profile_dependency_evidence(profile, live_ros_graph)
    if not evidence:
        return ""
    profile_path = sanitize_reason(os.environ.get("AGENTIC_VERIFY_BRIDGE_PROFILE_FILE") or "")
    prefix = f"profile_path={profile_path}; " if profile_path else ""
    return f"{prefix}profile_dependencies={evidence}"


def _load_bridge_profile() -> dict[str, object]:
    profile_path = Path(os.environ.get("AGENTIC_VERIFY_BRIDGE_PROFILE_FILE") or "")
    if not profile_path.exists():
        return {}
    try:
        import yaml
    except Exception:
        return {}
    try:
        with profile_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _ros_graph_snapshot() -> dict[str, list[str]]:
    return {
        "nodes": _ros_list(["ros2", "node", "list"]),
        "topics": _ros_list(["ros2", "topic", "list"]),
        "services": _ros_list(["ros2", "service", "list"]),
        "actions": _ros_list(["ros2", "action", "list"]),
        "errors": _ROS_GRAPH_QUERY_ERRORS,
    }


_ROS_GRAPH_QUERY_ERRORS: list[str] = []


def _ros_list(command: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        _ROS_GRAPH_QUERY_ERRORS.append(f"{' '.join(command)}:ros2_unavailable")
        return []
    except subprocess.TimeoutExpired:
        _ROS_GRAPH_QUERY_ERRORS.append(f"{' '.join(command)}:timeout")
        return []
    if result.returncode != 0:
        _ROS_GRAPH_QUERY_ERRORS.append(f"{' '.join(command)}:{summarize_cli_stderr(result.stderr)}")
        return []
    return [line.strip().split(" ", 1)[0] for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    skill_name = os.environ.get("AGENTIC_REAL_SCHEDULER_CAPABILITY", "robot.get_state")
    permissions = [item for item in os.environ.get("AGENTIC_REAL_SCHEDULER_CAPABILITY_PERMISSIONS", "robot.state.read").split(",") if item]
    server = None
    try:
        server = RuntimeServer.create()
        service = server.kernel_service
        capability_spec = server.registry.capabilities.get(skill_name)
        if capability_spec is None:
            return unverified(
                "SCHEDULER_CAPABILITY_UNAVAILABLE",
                f"configure a real capability manifest for {skill_name}",
            )
        preflight_error, preflight_next_action = preflight_ros_interface(capability_spec)
        if preflight_error:
            return unverified(preflight_error, preflight_next_action)
        agent = service.create_agent(app_id="scheduler_verify", session_id="scheduler_verify_capability", agent_id="agent_scheduler_verify_capability")
        service.start_agent(agent.agent_id)
        scheduler = EnvironmentAwareDAGScheduler(
            service.queue_store,
            service.managers,
            kernel_service=service,
            event_sink=service.event_sink,
            agent_lifecycle=service.agent_lifecycle,
            audit_logger=service.audit_logger,
            capability_registry=server.registry.capabilities,
        )
        node = TaskNode.create(
            node_id="verify_capability_node",
            task_graph_id="verify_capability_graph",
            user_goal_id="verify_capability_goal",
            agent_id=agent.agent_id,
            agent_name="scheduler_verify",
            app_id="scheduler_verify",
            session_id="scheduler_verify_capability",
            capability=skill_name,
            operation_type=skill_name,
            query_type=QueryType.ROBOT_CAPABILITY,
            required_permissions=permissions,
            resources=[ResourceRequest(resource_id="scheduler_verify_readonly", mode="shared", lease_ttl_ns=30_000_000_000)],
        )
        graph = TaskGraph.create(
            task_graph_id="verify_capability_graph",
            user_goal_id="verify_capability_goal",
            root_goal="verify real scheduler capability dispatch",
            agent_id=agent.agent_id,
            app_id="scheduler_verify",
            session_id="scheduler_verify_capability",
            nodes={"verify_capability_node": node},
        )
        response = scheduler.submit_graph(graph)
        if not response.success:
            return fail(
                response.error_code,
                f"fix scheduler admission/capability registry; metadata={response.metadata}",
            )

        decisions = scheduler.tick(max_dispatch=1)
        if not decisions:
            return fail(
                "SCHEDULER_DISPATCH_FAILED",
                "scheduler admitted graph but produced no dispatch decision",
            )
        decision = decisions[0]
        events = service.event_sink.recent(limit=100)
        recent_syscalls = service.recent_syscalls(limit=50)
        recent_audit_records = service.audit_logger.recent(limit=50) if service.audit_logger is not None else []
    except OSError as exc:
        return unverified(
            "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE",
            f"configure writable runtime verification roots; reason={exc}",
        )
    except Exception as exc:
        if os.environ.get("AGENTIC_VERIFY_VERBOSE"):
            traceback.print_exc()
        return fail(
            "SCHEDULER_REAL_CAPABILITY_VERIFY_FAILED",
            f"fix scheduler capability verification script or runtime contract; reason={exc}",
        )
    finally:
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass

    if decision.get("success") is True:
        dispatched_events = [
            event
            for event in events
            if event["event_type"] == "scheduler.node.dispatched"
            and event["metadata"].get("node_id") == "verify_capability_node"
        ]
        if not dispatched_events:
            return fail(
                "SCHEDULER_DISPATCH_FAILED",
                "ensure scheduler dispatch audit is emitted",
            )
        dispatched_metadata = dispatched_events[-1]["metadata"]
        dispatched_syscall_id = str(dispatched_metadata.get("syscall_id") or "")
        dispatched_lease_id = str(dispatched_metadata.get("resource_lease_id") or "")
        if not dispatched_syscall_id:
            return fail(
                "SCHEDULER_DISPATCH_FAILED",
                "ensure scheduler dispatch audit includes the real KernelSyscall ID",
            )
        if not dispatched_lease_id:
            return fail(
                "SCHEDULER_RESOURCE_UNAVAILABLE",
                "ensure scheduler dispatch audit includes acquired resource lease IDs",
            )
        matching_syscalls = [
            item
            for item in recent_syscalls
            if item.get("syscall_id") == dispatched_syscall_id
            and item.get("operation_type") == skill_name
        ]
        if not matching_syscalls:
            return fail(
                "SCHEDULER_DISPATCH_FAILED",
                "ensure KernelService recent syscalls include the dispatched scheduler capability syscall",
            )
        syscall_record = matching_syscalls[-1]
        if not syscall_record.get("success"):
            return fail(
                str(syscall_record.get("error_code") or "SCHEDULER_DISPATCH_FAILED"),
                "ensure the real capability syscall succeeds before reporting PASS",
            )
        audit_id = str(syscall_record.get("audit_id") or "")
        if not audit_id:
            return fail(
                "SCHEDULER_DISPATCH_FAILED",
                "ensure KernelService writes capability syscall audit records",
            )
        if not any(record.get("audit_id") == audit_id for record in recent_audit_records):
            return fail(
                "SCHEDULER_DISPATCH_FAILED",
                "ensure AuditLogger recent records include the capability syscall audit ID",
            )
        print("RESULT=PASS")
        print("ERROR_CODE=")
        print("NEXT_ACTION=")
        return 0

    error_code = str(decision.get("error_code") or "SCHEDULER_CAPABILITY_UNAVAILABLE")
    if error_code in {
        "ROS_BRIDGE_UNAVAILABLE",
        "ROS_SERVICE_UNAVAILABLE",
        "ROS_ACTION_UNAVAILABLE",
        "ROBOT_BACKEND_FAILED",
        "ROBOT_MANAGER_NOT_WIRED",
        "SKILL_BACKEND_UNAVAILABLE",
        "SKILL_TIMEOUT",
        "KERNEL_SYSCALL_TIMEOUT",
        "SCHEDULER_CAPABILITY_UNAVAILABLE",
        "SCHEDULER_REAL_DEPENDENCY_UNAVAILABLE",
    }:
        live_graph = _ros_graph_snapshot()
        next_action = dependency_next_action(
            error_code,
            decision,
            recent_syscalls,
            recent_audit_records,
            live_ros_graph=live_graph,
            bridge_profile=_load_bridge_profile(),
        )
        auto_start_hint = _readonly_state_bridge_auto_start_hint()
        if auto_start_hint:
            next_action = f"{next_action}; {auto_start_hint}"
        return unverified(
            error_code,
            next_action,
        )

    return fail(
        error_code,
        "fix scheduler capability dispatch or runtime capability contract",
    )


raise SystemExit(main())
PY
