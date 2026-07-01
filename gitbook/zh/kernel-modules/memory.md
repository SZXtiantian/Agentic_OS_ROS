# memory

Source: `agentic_runtime_src/agentic_os/kernel/memory`

`memory` 管理 App 记忆、检索、上下文注入和持久化 provider。

## App 可用入口

高层 SDK：

```python
await ctx.memory.remember("last_target", "green block")
value = await ctx.memory.recall("last_target")
```

进阶 API：

```python
await ctx.kernel.memory.remember(content, key="...", tags=[...])
await ctx.kernel.memory.add(content, key="...")
await ctx.kernel.memory.search(query, limit=5)
await ctx.kernel.memory.get(key)
await ctx.kernel.memory.update(key, content)
await ctx.kernel.memory.delete(key)
await ctx.kernel.memory.list(limit=100)
```

## 示例

```python
await ctx.kernel.memory.remember(
    result,
    key=f"{ctx.session_id}:color-block-result",
    tags=["color_block", "evidence"],
    timeout_s=5,
)
```

## 开发者注意

- 短期任务状态放 context。
- 可检索、可复用结果放 memory。
- 大文件和证据材料放 storage。
