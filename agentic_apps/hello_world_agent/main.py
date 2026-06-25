from __future__ import annotations

from typing import Any

from agentic_runtime.sdk import AgentContext


APP_ID = "hello_world_agent"
PLAN_SCHEMA_VERSION = "1.0"


async def run(ctx: AgentContext, **kwargs: Any) -> dict[str, Any]:
    task_text = str(kwargs.get("task_text") or kwargs.get("message") or "Say hello through Agentic OS.").strip()
    steps: list[dict[str, Any]] = []

    plan_result = await _plan_with_system_llm(ctx, task_text)
    steps.append(_llm_step("llm_plan", plan_result))
    if not plan_result["success"]:
        return _app_result(
            ctx,
            task_text,
            {},
            steps,
            str(plan_result["error_code"] or "HELLO_WORLD_LLM_REQUIRED"),
            str(plan_result["reason"] or "system LLM planning is required"),
        )

    plan = plan_result["plan"]
    validation = _validate_plan(plan)
    if not validation["success"]:
        steps.append({"name": "validate_plan", "success": False, **validation})
        return _app_result(
            ctx,
            task_text,
            plan,
            steps,
            str(validation["error_code"]),
            str(validation["reason"]),
        )
    steps.append({"name": "validate_plan", "success": True, "error_code": "", "reason": "", "data": {"planner_mode": "llm"}})

    context_put = await ctx.kernel.context.put("hello_world.plan", plan, timeout_s=5)
    steps.append(_step("context_put", context_put))

    context_get = await ctx.kernel.context.get("hello_world.plan", timeout_s=5)
    steps.append(_step("context_get", context_get))

    memory = await ctx.kernel.memory.remember(
        plan,
        key=str(plan["memory_key"]),
        tags=["hello_world", "llm_plan"],
        timeout_s=5,
    )
    steps.append(_step("memory_remember", memory))

    storage_mount = await ctx.kernel.storage.mount("hello_world", timeout_s=5)
    steps.append(_step("storage_mount", storage_mount))

    storage = await ctx.kernel.storage.write(str(plan["storage_path"]), plan, timeout_s=5)
    steps.append(_step("storage_write", storage))

    tool = await ctx.kernel.tool.call("calculator.add", dict(plan["tool_args"]), timeout_s=5)
    steps.append(_step("tool_calculator_add", tool))

    report = await ctx.kernel.skill.call("report.say", {"message": str(plan["report_message"])}, timeout_s=10)
    steps.append(_step("skill_report_say", report))

    failed = next((step for step in steps if not step["success"]), None)
    return _app_result(
        ctx,
        task_text,
        plan,
        steps,
        "" if failed is None else str(failed.get("error_code") or "HELLO_WORLD_STEP_FAILED"),
        "" if failed is None else str(failed.get("reason") or "Agentic execution step failed"),
    )


async def _plan_with_system_llm(ctx: AgentContext, task_text: str) -> dict[str, Any]:
    result = await ctx.llm.chat_json(
        system_prompt=_system_prompt(),
        user_prompt=f"User task: {task_text}",
        timeout_s=20,
    )
    if not result.success:
        return {
            "success": False,
            "plan": {},
            "error_code": result.error_code or "HELLO_WORLD_LLM_REQUIRED",
            "reason": result.reason or "system LLM planning is required",
            "metadata": dict(result.metadata),
        }
    return {"success": True, "plan": dict(result.plan), "error_code": "", "reason": "", "metadata": dict(result.metadata)}


def _system_prompt() -> str:
    return "\n".join(
        [
            "You plan a Hello World Agentic App task.",
            "Return one raw JSON object only.",
            "Required fields:",
            "- schema_version: '1.0'",
            "- planner_mode: 'llm'",
            "- greeting: short user-facing greeting",
            "- report_message: short message for report.say",
            "- memory_key: stable memory key",
            "- storage_path: path under hello_world/",
            "- tool_args: object with integer a and integer b for calculator.add",
            "- user_summary: one sentence summary",
            "Do not include markdown fences.",
        ]
    )


def _validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    required = ["schema_version", "planner_mode", "greeting", "report_message", "memory_key", "storage_path", "tool_args", "user_summary"]
    missing = [field for field in required if field not in plan]
    if missing:
        return {
            "error_code": "HELLO_WORLD_LLM_PLAN_INVALID",
            "reason": f"LLM plan missing required fields: {', '.join(missing)}",
        }
    if plan["schema_version"] != PLAN_SCHEMA_VERSION or plan["planner_mode"] != "llm":
        return {"error_code": "HELLO_WORLD_LLM_PLAN_INVALID", "reason": "LLM plan schema_version/planner_mode invalid"}
    if not str(plan["storage_path"]).startswith("hello_world/"):
        return {"error_code": "HELLO_WORLD_LLM_PLAN_INVALID", "reason": "LLM plan storage_path must stay under hello_world/"}
    tool_args = plan["tool_args"]
    if not isinstance(tool_args, dict) or not isinstance(tool_args.get("a"), int) or not isinstance(tool_args.get("b"), int):
        return {"error_code": "HELLO_WORLD_LLM_PLAN_INVALID", "reason": "LLM plan tool_args must contain integer a and b"}
    for field in ["greeting", "report_message", "memory_key", "storage_path", "user_summary"]:
        if not isinstance(plan[field], str) or not plan[field].strip():
            return {"error_code": "HELLO_WORLD_LLM_PLAN_INVALID", "reason": f"LLM plan field {field} must be a non-empty string"}
    return {"success": True, "error_code": "", "reason": ""}


def _app_result(
    ctx: AgentContext,
    task_text: str,
    plan: dict[str, Any],
    steps: list[dict[str, Any]],
    error_code: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "success": not error_code,
        "app_id": ctx.app_manifest.name or APP_ID,
        "planner_mode": str(plan.get("planner_mode", "")),
        "task_text": task_text,
        "message": str(plan.get("greeting") or ""),
        "plan": plan,
        "steps": steps,
        "error_code": error_code,
        "reason": reason,
        "syscall_ids": [step["syscall_id"] for step in steps if step.get("syscall_id")],
        "audit_ids": [step["audit_id"] for step in steps if step.get("audit_id")],
    }


def _llm_step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "success": bool(result["success"]),
        "error_code": str(result.get("error_code") or ""),
        "reason": str(result.get("reason") or ""),
        "syscall_id": "",
        "audit_id": "",
        "data": {"plan": dict(result.get("plan") or {}), "metadata": dict(result.get("metadata") or {})},
    }


def _step(name: str, result: Any) -> dict[str, Any]:
    summary = _result_summary(result)
    return {"name": name, **summary}


def _result_summary(result: Any) -> dict[str, Any]:
    response = getattr(result, "response", None)
    payload = _response_payload(response)
    error_code = str(getattr(result, "error_code", "") or payload.get("error_code", ""))
    reason = str(payload.get("reason") or payload.get("message") or "")
    audit_id = str(getattr(result, "audit_id", "") or payload.get("audit_id") or "")
    nested = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    if not audit_id and nested:
        audit_id = str(nested.get("audit_id") or "")
    return {
        "success": bool(getattr(result, "success", False)),
        "error_code": error_code,
        "reason": reason,
        "syscall_id": str(getattr(result, "syscall_id", "") or ""),
        "audit_id": audit_id,
        "data": payload,
    }


def _response_payload(response: Any) -> dict[str, Any]:
    data = getattr(response, "data", None)
    if isinstance(data, dict) and data:
        return dict(data)
    metadata = getattr(response, "metadata", None)
    if isinstance(metadata, dict) and metadata:
        return dict(metadata)
    if isinstance(response, dict):
        return dict(response)
    return {}
