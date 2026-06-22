from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs):
    message = str(kwargs.get("message") or "app_template kernel smoke executed")
    context_put = await ctx.kernel.context.put("template.message", message, timeout_s=5)
    context_get = await ctx.kernel.context.get("template.message", timeout_s=5)
    memory = await ctx.kernel.memory.remember(message, key=f"{ctx.session_id}:template-message", tags=["smoke"], timeout_s=5)
    await ctx.kernel.storage.mount("template", timeout_s=5)
    storage = await ctx.kernel.storage.write(f"template/{ctx.session_id}.md", message, timeout_s=5)
    tool = await ctx.kernel.tool.call("calculator.add", {"a": 2, "b": 3}, timeout_s=5)
    report = await ctx.kernel.skill.call("report.say", {"message": message}, timeout_s=10)

    results = {
        "context_put": _result_summary(context_put),
        "context_get": _result_summary(context_get),
        "memory": _result_summary(memory),
        "storage": _result_summary(storage),
        "tool": _result_summary(tool),
        "report": _result_summary(report),
    }
    return {
        "success": all(results[name]["success"] for name in ("context_put", "context_get", "memory", "storage", "tool", "report")),
        "results": results,
    }


def _result_summary(result):
    response = result.response
    data = getattr(response, "data", response)
    return {
        "success": result.success,
        "error_code": result.error_code,
        "syscall_id": result.syscall_id,
        "audit_id": result.audit_id,
        "data": data,
    }
