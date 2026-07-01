# Agentic OS Docs

Agentic OS is an Agentic Runtime above ROS2. It is not a ROS2 app, not an LLM wrapper, and not a ROS2 fork. It exposes high-level, permissioned, safe, auditable robot capabilities to Agent Apps.

Agent Apps call the Runtime-injected `AgentContext`:

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    state = await ctx.robot.get_state()
    return {"success": True, "state": state.to_dict()}
```

## Core Boundaries

- Agent Apps must not `import rclpy`.
- Agent Apps must not publish `/cmd_vel`.
- Agent Apps must not subscribe to `/scan`, `/odom`, or `/tf` directly.
- Agent Apps must not call Nav2 or MoveIt actions directly.
- Robot motion must pass through Runtime permissions, resource locks, safety guards, and audit logs.

## API Groups

- [Robot API](sdk/robot-api/README.md)
- [World API](sdk/world-api/README.md)
- [Memory API](sdk/memory-api/README.md)
- [Human API](sdk/human-api/README.md)
- [Report API](sdk/report-api/README.md)
- [LLM API](sdk/llm-api/README.md)
- [Perception API](sdk/perception-api/README.md)
- [Arm API](sdk/arm-api/README.md)
- [Gripper API](sdk/gripper-api/README.md)
- [Storage API](sdk/storage-api/README.md)
- [Agentic System Calls](sdk/kernel-api/README.md)
- [Kernel Modules](kernel-modules/README.md)
