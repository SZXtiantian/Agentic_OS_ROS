# hooks

Source: `agentic_runtime_src/agentic_os/kernel/hooks`

`hooks` 提供 Runtime 内部事件、队列、metrics 和 queue store。

## App 可用入口

当前暂无直接 App API。

## 当前状态

该模块由 Runtime、scheduler、manager 和测试使用。robot lanes 与 generic tool lanes 分离，机器人运动不能通过 generic tool lane 绕过安全链。

## 开发者注意

- App 不应该直接操作 kernel queue。
- 需要记录业务状态时，用 `ctx.kernel.context.*`、`ctx.kernel.storage.*` 或 `ctx.report.*`。
- 面向 App 的事件订阅 API 会在后续完善。
