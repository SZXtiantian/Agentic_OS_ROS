from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs):
    del kwargs
    await ctx.report.say("app_template executed")
    return {"success": True}
