#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "${AGENTIC_VERIFY_REAL_SCHEDULER_LLM:-0}" = "1" ]; then
  eval "$(PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

import os
import shlex

from agentic_runtime.llm.config import load_llm_config

missing = [
    name
    for name in ("AGENTIC_REAL_LLM_BASE_URL", "AGENTIC_REAL_LLM_API_KEY", "AGENTIC_REAL_LLM_MODEL")
    if not os.environ.get(name)
]
if missing:
    try:
        cfg = load_llm_config().require_ready()
    except Exception:
        raise SystemExit(0)
    values = {
        "AGENTIC_REAL_LLM_BASE_URL": cfg.base_url,
        "AGENTIC_REAL_LLM_API_KEY": cfg.api_key,
        "AGENTIC_REAL_LLM_MODEL": cfg.model,
    }
    for name in missing:
        if values.get(name):
            print(f"export {name}={shlex.quote(str(values[name]))}")
PY
)"
fi

missing=()
[ "${AGENTIC_VERIFY_REAL_SCHEDULER_LLM:-0}" = "1" ] || missing+=("AGENTIC_VERIFY_REAL_SCHEDULER_LLM")
[ -n "${AGENTIC_REAL_LLM_BASE_URL:-}" ] || missing+=("AGENTIC_REAL_LLM_BASE_URL")
[ -n "${AGENTIC_REAL_LLM_API_KEY:-}" ] || missing+=("AGENTIC_REAL_LLM_API_KEY")
[ -n "${AGENTIC_REAL_LLM_MODEL:-}" ] || missing+=("AGENTIC_REAL_LLM_MODEL")

echo "CHECK_NAME=real_scheduler_llm"
echo "REQUIRED_ENV=AGENTIC_VERIFY_REAL_SCHEDULER_LLM=1,AGENTIC_REAL_LLM_BASE_URL,AGENTIC_REAL_LLM_API_KEY,AGENTIC_REAL_LLM_MODEL"

if [ "${#missing[@]}" -gt 0 ]; then
  joined="$(IFS=,; echo "${missing[*]}")"
  echo "RESULT=UNVERIFIED_REAL_DEPENDENCY"
  echo "ERROR_CODE=UNVERIFIED_REAL_DEPENDENCY"
  echo "NEXT_ACTION=set real OpenAI-compatible endpoint env vars and AGENTIC_VERIFY_REAL_SCHEDULER_LLM=1; missing=${joined}"
  exit 2
fi

PYTHONPATH="${PYTHONPATH:-.}" python - <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

from agentic_os.kernel.access import AccessDecision
from agentic_os.kernel.scheduler import QueryType, TaskGraph, TaskNode
from agentic_os.kernel.system_call import ContextQuery
from agentic_runtime.audit import AuditLogger
from agentic_runtime.kernel_service import KernelService


class Config:
    scheduler_policy = "fifo"
    storage_root = os.environ.get("AGENTIC_SCHEDULER_VERIFY_STORAGE", "/tmp/agentic_scheduler_verify_llm")
    kernel = {
        "scheduler_policy": "env_aware_priority_dag",
        "llm": {
            "configs": [
                {
                    "name": "real-scheduler-llm",
                    "backend": "openai_compatible",
                    "base_url": os.environ["AGENTIC_REAL_LLM_BASE_URL"],
                    "api_key_env": "AGENTIC_REAL_LLM_API_KEY",
                    "model": os.environ["AGENTIC_REAL_LLM_MODEL"],
                    "enabled": True,
                    "capabilities": ["chat", "scheduler_planning"],
                    "supports_json": True,
                    "timeout_s": float(os.environ.get("AGENTIC_REAL_LLM_TIMEOUT_S", "45")),
                }
            ]
        },
    }


class SchedulerLLMVerificationInterventionProvider:
    def request_confirmation(self, request):
        if (
            os.environ.get("AGENTIC_VERIFY_REAL_SCHEDULER_LLM") == "1"
            and request.resource.resource_type == "llm"
            and request.resource.resource_id == "external_provider"
        ):
            return AccessDecision(
                allowed=True,
                reason="real scheduler LLM verification opt-in approved external provider call",
                requires_intervention=True,
                intervention_id="ivn_real_scheduler_llm",
                metadata={"approval_env": "AGENTIC_VERIFY_REAL_SCHEDULER_LLM"},
            )
        return AccessDecision(
            allowed=False,
            error_code="ACCESS_INTERVENTION_REQUIRED",
            reason="real scheduler LLM verification only approves external LLM provider calls",
            requires_intervention=True,
            intervention_id="ivn_real_scheduler_llm_denied",
        )


audit_logger = AuditLogger(Path(Config.storage_root) / "scheduler_verify_audit.jsonl")
service = KernelService(config=Config(), audit_logger=audit_logger)
service.access_manager.intervention_provider = SchedulerLLMVerificationInterventionProvider()
agent = service.create_agent(app_id="scheduler_verify", session_id="scheduler_verify_llm", agent_id="agent_scheduler_verify_llm")
service.start_agent(agent.agent_id)
seed_response = service.execute_request(
    "scheduler_verify",
    ContextQuery(
        operation_type="ctx_put",
        params={
            "namespace": "scheduler_verify",
            "session_id": "scheduler_verify_llm",
            "key": "verified_context",
            "value": {"summary": "scheduler fusion verification context"},
        },
        namespace="scheduler_verify",
        session_id="scheduler_verify_llm",
        metadata={
            "agent_id": agent.agent_id,
            "app_id": "scheduler_verify",
            "session_id": "scheduler_verify_llm",
            "permissions": [],
        },
    ),
    timeout_s=30,
)
if not seed_response.success:
    service.stop()
    print("RESULT=FAIL")
    print(f"ERROR_CODE={seed_response.error_code}")
    print("NEXT_ACTION=fix real scheduler LLM verification context provider")
    sys.exit(1)

producer = TaskNode.create(
    node_id="verified_context_source",
    task_graph_id="verify_existing_context_graph",
    user_goal_id="goal_verify_existing_context",
    agent_id=agent.agent_id,
    agent_name="scheduler_verify",
    app_id="scheduler_verify",
    session_id="scheduler_verify_llm",
    capability="context.get",
    operation_type="ctx_get",
    query_type=QueryType.CONTEXT,
    params={
        "namespace": "scheduler_verify",
        "session_id": "scheduler_verify_llm",
        "key": "verified_context",
    },
    metadata={
        "produces_fact_specs": [
            {
                "fact_key": "verified_context",
                "value_key": "value",
                "ttl_ns": 30_000_000_000,
                "confidence": 0.99,
            }
        ]
    },
    produces_facts=["verified_context"],
)
producer_graph = TaskGraph.create(
    task_graph_id="verify_existing_context_graph",
    user_goal_id="goal_verify_existing_context",
    root_goal="existing verified context",
    agent_id=agent.agent_id,
    app_id="scheduler_verify",
    session_id="scheduler_verify_llm",
    nodes={producer.node_id: producer},
)
producer_response = service.scheduler.submit_graph(producer_graph)
if not producer_response.success:
    service.stop()
    print("RESULT=FAIL")
    print(f"ERROR_CODE={producer_response.error_code}")
    print(f"NEXT_ACTION=fix scheduler context fact producer admission; metadata={producer_response.metadata}")
    sys.exit(1)
producer_decisions = service.scheduler.tick(max_dispatch=1)
if not producer_decisions or not producer_decisions[0].get("success"):
    service.stop()
    error_code = str((producer_decisions[0] if producer_decisions else {}).get("error_code") or "SCHEDULER_FACT_SOURCE_UNVERIFIED")
    print("RESULT=FAIL")
    print(f"ERROR_CODE={error_code}")
    print("NEXT_ACTION=ensure scheduler context fact producer dispatches through KernelService and ingests a verified fact")
    sys.exit(1)
verified_fact = service.scheduler.environment_store.get("verified_context")
recent_audit_records = service.audit_logger.recent(limit=100) if service.audit_logger is not None else []
recent_syscalls = service.recent_syscalls(limit=100)
if verified_fact is None or not verified_fact.source_is_verified():
    service.stop()
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_FACT_SOURCE_UNVERIFIED")
    print("NEXT_ACTION=ensure scheduler LLM verification fact is produced by a real KernelService-dispatched TaskNode")
    sys.exit(1)
if not any(
    item.get("syscall_id") == verified_fact.source_syscall_id
    and item.get("operation_type") == "ctx_get"
    for item in recent_syscalls
):
    service.stop()
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_DISPATCH_FAILED")
    print("NEXT_ACTION=ensure KernelService recent syscalls include the verified context fact producer")
    sys.exit(1)
if not any(record.get("audit_id") == verified_fact.source_audit_id for record in recent_audit_records):
    service.stop()
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_FACT_SOURCE_UNVERIFIED")
    print("NEXT_ACTION=ensure AuditLogger records the verified context fact producer syscall")
    sys.exit(1)

response = service.scheduler.submit_goal(
    "Generate a safe AgenticOS TaskGraph containing exactly one report.say node that reports scheduler verification complete.",
    agent_id=agent.agent_id,
    app_id="scheduler_verify",
    session_id="scheduler_verify_llm",
)
if not response.success:
    service.stop()
    print("RESULT=FAIL")
    print(f"ERROR_CODE={response.error_code}")
    print(f"NEXT_ACTION=fix real LLM provider/schema output; metadata={response.metadata}")
    sys.exit(1)

consumer = TaskNode.create(
    node_id="verified_context_consumer",
    task_graph_id="verify_fusion_context_graph",
    user_goal_id="goal_verify_fusion_context",
    agent_id=agent.agent_id,
    agent_name="scheduler_verify",
    app_id="scheduler_verify",
    session_id="scheduler_verify_llm",
    capability="report.say",
    operation_type="skill_call",
    query_type=QueryType.SKILL,
    consumes_facts=["verified_context"],
)
consumer_graph = TaskGraph.create(
    task_graph_id="verify_fusion_context_graph",
    user_goal_id="goal_verify_fusion_context",
    root_goal="reuse verified context",
    agent_id=agent.agent_id,
    app_id="scheduler_verify",
    session_id="scheduler_verify_llm",
    nodes={consumer.node_id: consumer},
)
fusion_response = service.scheduler.submit_graph(consumer_graph)
events = service.event_sink.recent(limit=200)
recent_syscalls = service.recent_syscalls(limit=100)
service.stop()

if not fusion_response.success:
    print("RESULT=FAIL")
    print(f"ERROR_CODE={fusion_response.error_code}")
    print(f"NEXT_ACTION=fix real scheduler fusion LLM explanation path; metadata={fusion_response.metadata}")
    sys.exit(1)

if not any(event["event_type"] == "scheduler.llm.real_call_completed" for event in events):
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_LLM_REAL_PROVIDER_REQUIRED")
    print("NEXT_ACTION=ensure scheduler LLM call completes through KernelService and emits audit")
    sys.exit(1)

if not any(
    item.get("operation_type") == "scheduler_generate_task_graph" and item.get("queue_name") == "llm"
    for item in recent_syscalls
):
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_LANE_UNSUPPORTED")
    print("NEXT_ACTION=ensure TaskGraphPlanner uses KernelService LLMQuery on the llm queue")
    sys.exit(1)

if not any(
    item.get("operation_type") == "scheduler_explain_fusion_plan" and item.get("queue_name") == "llm"
    for item in recent_syscalls
):
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_LLM_REAL_PROVIDER_REQUIRED")
    print("NEXT_ACTION=ensure fusion reasoning uses KernelService LLMQuery on the llm queue")
    sys.exit(1)

if not any(
    event["event_type"] == "scheduler.llm.real_call_completed"
    and event["metadata"].get("operation_type") == "scheduler_explain_fusion_plan"
    and event["metadata"].get("schema_id") == "fusion_reasoning.schema.json"
    for event in events
):
    print("RESULT=FAIL")
    print("ERROR_CODE=SCHEDULER_LLM_OUTPUT_SCHEMA_INVALID")
    print("NEXT_ACTION=ensure real scheduler fusion explanation returns fusion_reasoning.schema.json")
    sys.exit(1)

print("RESULT=PASS")
print("ERROR_CODE=")
print("NEXT_ACTION=")
PY
