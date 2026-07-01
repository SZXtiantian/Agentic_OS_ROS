# Runtime 概览

Agentic Runtime 是 Agent App 和 ROS2 之间的安全执行层。

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> Agentic OS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

Runtime 负责：

- 加载 `app.yaml`
- 校验权限和 capability
- 执行 access/intervention
- 管理机器人资源锁
- 调用 safety guard
- 调度 system skill
- 写 session、syscall 和 audit log

Agent App 只应该编排任务级能力，不应该实现实时控制。
