# context

Source: `agentic_runtime_src/agentic_os/kernel/context`

`context` 管理 session context、恢复 metadata 和 LLM generation context。generation context 只用于 LLM 工作，不用于暂停或恢复真实机器人运动。

## App 可用入口

```python
await ctx.kernel.context.put(key, value, timeout_s=5)
await ctx.kernel.context.get(key, timeout_s=5)
await ctx.kernel.context.delete(key, timeout_s=5)
await ctx.kernel.context.list(prefix="", limit=100, timeout_s=5)
await ctx.kernel.context.snapshot(state=None, checkpoint="default", timeout_s=5)
await ctx.kernel.context.recover(session_id="", checkpoint="", timeout_s=5)
await ctx.kernel.context.compact(max_tokens=2000, timeout_s=5)
await ctx.kernel.context.clear(scope="session", timeout_s=5)
```

## 示例

```python
await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
```

## 开发者注意

- 用 context 保存当前任务阶段、计划、临时状态。
- 不要用 context 承诺机器人动作可自动恢复。
- 需要长期保存的结果应写入 memory/storage。
