#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

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

PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

import os
import sys
import traceback

from agentic_os.kernel.scheduler import EnvironmentAwareDAGScheduler, QueryType, ResourceRequest, TaskGraph, TaskNode
from agentic_runtime.server import RuntimeServer


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


def main() -> int:
    skill_name = os.environ.get("AGENTIC_REAL_SCHEDULER_CAPABILITY", "robot.get_state")
    permissions = [item for item in os.environ.get("AGENTIC_REAL_SCHEDULER_CAPABILITY_PERMISSIONS", "robot.state.read").split(",") if item]
    server = None
    try:
        server = RuntimeServer.create()
        service = server.kernel_service
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
        return unverified(
            error_code,
            "configure and verify the real bridge/backend for the selected capability",
        )

    return fail(
        error_code,
        "fix scheduler capability dispatch or runtime capability contract",
    )


raise SystemExit(main())
PY
