# Agentic OS 文档

Agentic OS 向 Agent Apps 暴露高层、带权限、安全、可审计的机器人能力。当前 GitBook 暂时只展示中文文档；英文文档文件仍保留在仓库中，后续需要双语展示时再恢复导航入口。

进入文档：

- [中文文档](zh/README.md)

API 文档围绕 `AgentContext` namespace 组织：

- `ctx.robot`
- `ctx.world`
- `ctx.memory`
- `ctx.human`
- `ctx.report`
- `ctx.llm`
- `ctx.perception`
- `ctx.arm`
- `ctx.gripper`
- `ctx.storage`
- `ctx.kernel`

Kernel 内部也会按照 `agentic_runtime_src/agentic_os/kernel` 源码目录说明，方便开发者把 App 可用 API 对应回 Runtime 实现边界。

Agent App 不允许导入 ROS2 库，不允许发布机器人 topic，不允许直接调用 Nav2 或 MoveIt，也不允许执行实时闭环控制。所有机器人动作都必须经过 Agentic Runtime 的权限检查、access/intervention、资源锁、安全守卫和审计日志。
