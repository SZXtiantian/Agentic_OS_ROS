# system_call

Source: `agentic_runtime_src/agentic_os/kernel/system_call`

`system_call` 是 Runtime 内部统一执行模型。`ctx.kernel.*`、SDK 和 system skill 最终都会变成受控 syscall。

## App 可用入口

App 不直接构造底层 syscall 对象，而是通过：

```python
await ctx.kernel.context.put(...)
await ctx.kernel.memory.remember(...)
await ctx.kernel.storage.write(...)
await ctx.kernel.skill.call(...)
await ctx.kernel.tool.call(...)
await ctx.kernel.llm.chat(...)
```

这些调用统一返回 `KernelSDKResult`：

```python
KernelSDKResult(
    success=True,
    response={},
    error_code="",
    syscall_id="...",
    audit_id="...",
)
```

## 开发者注意

- 结果里保留 `syscall_id` 和 `audit_id`。
- 错误必须使用结构化 `error_code`。
- 不要直接调用 Runtime manager 绕过 syscall 执行链。
