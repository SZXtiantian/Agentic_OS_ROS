from __future__ import annotations

from typing import Any

from agentic_runtime.sdk import AgentContext


APP_ID = "hello_world_agent"


async def run(ctx: AgentContext, **kwargs: Any) -> dict[str, Any]:
    message = str(kwargs.get("message") or "Hello from a template-derived Agentic App.")
    steps: list[dict[str, Any]] = []

    context_put = await ctx.kernel.context.put("hello_world.message", message, timeout_s=5)
    steps.append(_step("context_put", context_put))

    context_get = await ctx.kernel.context.get("hello_world.message", timeout_s=5)
    steps.append(_step("context_get", context_get))

    memory = await ctx.kernel.memory.remember(
        message,
        key=f"{ctx.session_id}:hello-world-message",
        tags=["hello_world", "template_derived"],
        timeout_s=5,
    )
    steps.append(_step("memory_remember", memory))

    storage_mount = await ctx.kernel.storage.mount("hello_world", timeout_s=5)
    steps.append(_step("storage_mount", storage_mount))

    storage = await ctx.kernel.storage.write(f"hello_world/{ctx.session_id}.md", message, timeout_s=5)
    steps.append(_step("storage_write", storage))

    tool = await ctx.kernel.tool.call("calculator.add", {"a": 2, "b": 3}, timeout_s=5)
    steps.append(_step("tool_calculator_add", tool))

    report = await ctx.kernel.skill.call("report.say", {"message": message}, timeout_s=10)
    steps.append(_step("skill_report_say", report))

    return _app_result(ctx, message, steps)


def _app_result(ctx: AgentContext, message: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    failed = next((step for step in steps if not step["success"]), None)
    return {
        "schema_version": "1.0",
        "success": failed is None,
        "app_id": ctx.app_manifest.name or APP_ID,
        "message": message,
        "steps": steps,
        "error_code": "" if failed is None else str(failed.get("error_code") or "HELLO_WORLD_STEP_FAILED"),
        "reason": "" if failed is None else str(failed.get("reason") or "Agentic kernel smoke step failed"),
        "syscall_ids": [step["syscall_id"] for step in steps if step.get("syscall_id")],
        "audit_ids": [step["audit_id"] for step in steps if step.get("audit_id")],
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
