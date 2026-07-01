# Agentic SDK

Agentic SDK is the Python interface used directly by Agent App code. Runtime injects an `AgentContext`, and the app uses `ctx` to request capabilities protected by permissions, safety checks, resource locks, and audit logs.

Agent Apps do not import `rclpy`, publish `/cmd_vel`, call Nav2 or MoveIt directly, or talk to robot vendor drivers.

## SDK Namespaces

| Namespace | Purpose |
| --- | --- |
| `ctx.robot` | Read robot state, navigate, inspect an area, stop |
| `ctx.world` | Resolve place names into Runtime-usable locations |
| `ctx.perception` | Observe the environment, capture photos, read perception results |
| `ctx.arm` | Read arm state and run named arm motions |
| `ctx.gripper` | Open, close, or set controlled gripper commands |
| `ctx.memory` | Store and recall small pieces of app data |
| `ctx.storage` | Query app-visible evidence records; currently exposes recent photo records |
| `ctx.human` | Ask a human or request confirmation |
| `ctx.report` | Report progress and results |
| `ctx.llm` | Ask Runtime to run structured LLM calls |

`ctx.kernel.*` is not part of the Agentic SDK getting-started surface. It is the Agentic System Call facade for apps that need to issue Kernel system calls directly.

## Result Behavior

SDK methods return dataclasses, plain Python values, or `SkillResult` on success. Failures usually raise `AgenticRuntimeError` or a subclass.

The basic `SkillResult` shape is:

```python
SkillResult(
    success: bool,
    data: dict,
    error_code: str = "",
    reason: str = "",
    recoverable: bool = True,
    suggested_recovery: list[str] = [],
    audit_id: str = "",
)
```

## Example

```python
from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, place: str = "kitchen") -> dict:
    try:
        resolved = await ctx.world.resolve_place(place)
        await ctx.robot.navigate_to(resolved.name, timeout_s=120)
        inspection = await ctx.robot.inspect_area(resolved.name, timeout_s=60)
        await ctx.memory.remember("last_inspection", inspection.to_dict())
        await ctx.report.say(f"{resolved.name} inspection completed.")
        return {"success": True, "inspection": inspection.to_dict()}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```
