# agent

Source: `agentic_runtime_src/agentic_os/kernel/agent`

`agent` 目录包含 agent lifecycle、resource table、cleanup 和错误模型。

## App 可用入口

当前暂无稳定的直接 App API。Agent App 不应该 import 这里的 lifecycle/table/resource 内部类。

## 当前状态

该模块由 Runtime 内部使用，用于管理 agent/session 生命周期和资源清理。面向 App 的生命周期查询、暂停、恢复、清理接口会在后续完善。

## 开发者注意

- App 的入口仍然是 `app.yaml` 的 `entrypoint`。
- App 通过返回结构化结果表达成功或失败。
- Runtime 负责 session 和 agent 资源回收。
