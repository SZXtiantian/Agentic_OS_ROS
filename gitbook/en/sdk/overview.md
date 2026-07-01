# Agent App SDK Overview

The Agent App SDK is accessed through the Runtime-injected `AgentContext`. Apps do not touch ROS2 directly; they call high-level namespaces.

| Namespace | Purpose |
| --- | --- |
| `ctx.robot` | Robot state, navigation, inspection, stop |
| `ctx.world` | Place resolution and world-model reads |
| `ctx.memory` | App-level key-value memory |
| `ctx.human` | Human questions and confirmations |
| `ctx.report` | User-facing or runtime report messages |
| `ctx.llm` | Runtime-owned JSON planning |
| `ctx.perception` | Observation, photo capture, evidence |
| `ctx.arm` | Arm state and named actions |
| `ctx.gripper` | Gripper open, close, and controlled commands |
| `ctx.storage` | Runtime-managed photo/evidence index |
| `ctx.kernel` | Advanced syscall facade |

## Result Model

Low-level skills return:

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

High-level SDK calls return dataclasses or `SkillResult` on success and usually raise `AgenticRuntimeError` subclasses on failure.

## Minimal Example

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
