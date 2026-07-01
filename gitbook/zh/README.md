# Agentic OS 文档

Agentic OS 是运行在 ROS2 之上的 Agentic Runtime。它不是 ROS2 应用、不是 LLM wrapper，也不是 ROS2 fork；它的目标是向 Agent App 暴露高层、带权限、安全、可审计的机器人能力。

开发者只应该通过 `AgentContext` 调用 SDK：

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    state = await ctx.robot.get_state()
    return {"success": True, "state": state.to_dict()}
```

## 核心边界

- Agent App 不允许 `import rclpy`。
- Agent App 不允许发布 `/cmd_vel`。
- Agent App 不允许直接订阅 `/scan`、`/odom`、`/tf`。
- Agent App 不允许直接调用 Nav2 或 MoveIt action。
- 所有机器人运动必须经过 Runtime 的权限检查、资源锁、安全守卫和审计日志。

## API 分组

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
- [Kernel API](sdk/kernel-api/README.md)
