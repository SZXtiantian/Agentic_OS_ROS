from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs):
    del kwargs
    await ctx.report.say("robotic_coding_agent skeleton")
    return {"success": True, "skeleton": True}
