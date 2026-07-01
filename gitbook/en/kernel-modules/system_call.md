# system_call

Source: `agentic_runtime_src/agentic_os/kernel/system_call`

`system_call` is the Runtime-internal unified execution model. `ctx.kernel.*`, SDK calls, and system skills eventually become controlled syscalls.

## App-Facing Entry

Apps do not construct low-level syscall objects directly. Use:

```python
await ctx.kernel.context.put(...)
await ctx.kernel.memory.remember(...)
await ctx.kernel.storage.write(...)
await ctx.kernel.skill.call(...)
await ctx.kernel.tool.call(...)
await ctx.kernel.llm.chat(...)
```

These calls return `KernelSDKResult`:

```python
KernelSDKResult(
    success=True,
    response={},
    error_code="",
    syscall_id="...",
    audit_id="...",
)
```

## Notes

- Preserve `syscall_id` and `audit_id` in results.
- Errors must use structured `error_code` values.
- Do not call Runtime managers directly to bypass the syscall chain.
