# context

Source: `agentic_runtime_src/agentic_os/kernel/context`

`context` manages session context, recovery metadata, and LLM generation context. Generation context is for LLM work only; it does not suspend or resume real robot motion.

## App-Facing Entry

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

## Example

```python
await ctx.kernel.context.put("color_block_grasper.task", task, timeout_s=5)
```

## Notes

- Use context for current task phase, plan, and temporary state.
- Do not use context to promise automatic robot-motion recovery.
- Persist long-lived results in memory or storage.
