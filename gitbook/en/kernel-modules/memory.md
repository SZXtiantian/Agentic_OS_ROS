# memory

Source: `agentic_runtime_src/agentic_os/kernel/memory`

`memory` manages app memory, retrieval, context injection, and persistent providers.

## App-Facing Entry

High-level SDK:

```python
await ctx.memory.remember("last_target", "green block")
value = await ctx.memory.recall("last_target")
```

Advanced API:

```python
await ctx.kernel.memory.remember(content, key="...", tags=[...])
await ctx.kernel.memory.add(content, key="...")
await ctx.kernel.memory.search(query, limit=5)
await ctx.kernel.memory.get(key)
await ctx.kernel.memory.update(key, content)
await ctx.kernel.memory.delete(key)
await ctx.kernel.memory.list(limit=100)
```

## Example

```python
await ctx.kernel.memory.remember(
    result,
    key=f"{ctx.session_id}:color-block-result",
    tags=["color_block", "evidence"],
    timeout_s=5,
)
```

## Notes

- Put short-lived task state in context.
- Put reusable or searchable results in memory.
- Put large files and evidence artifacts in storage.
