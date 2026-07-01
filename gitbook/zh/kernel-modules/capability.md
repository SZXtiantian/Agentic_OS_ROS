# capability

Source: `agentic_runtime_src/agentic_os/kernel/capability`

`capability` 负责把稳定的 Agent API、manifest 声明和 skill contract 映射到 Runtime/bridge 能力。

## App 可用入口

没有直接的 `ctx.kernel.capability.*` App API。App 通过这些方式间接使用：

- `app.yaml` 的 `permissions`
- `app.yaml` 的 `required_capabilities`
- `agentic_runtime_src/system_skills/*/SKILL.md`
- SDK namespace，例如 `ctx.robot.*`、`ctx.perception.*`

## 当前状态

当前主要用于 Runtime capability preflight 和 skill/capability registry。后续会完善面向开发者的 capability 查询与诊断接口。

## 开发者注意

新增 App 时先在 manifest 声明 capability，再在代码里调用对应 SDK 或 skill。不要在 App 中硬编码 ROS2 service/action 名称。
