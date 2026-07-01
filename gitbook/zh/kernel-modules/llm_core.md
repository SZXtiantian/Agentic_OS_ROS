# llm_core

Source: `agentic_runtime_src/agentic_os/kernel/llm_core`

`llm_core` 是 ROS-free 的 LLM syscall 和 provider adapter 层。它负责 provider metadata、routing、active call 状态、取消和错误归一化。

## App 可用入口

普通 JSON 规划优先使用：

```python
result = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    timeout_s=30,
)
```

进阶 syscall facade：

```python
await ctx.kernel.llm.chat(messages, timeout_s=30)
await ctx.kernel.llm.complete(prompt, timeout_s=30)
await ctx.kernel.llm.embed(texts, timeout_s=30)
await ctx.kernel.llm.status(call_id="")
await ctx.kernel.llm.cancel(call_id="")
```

## 开发者注意

- LLM 只能做计划、解释、摘要或非实时推理。
- LLM 不能直接执行机器人闭环控制。
- 示例 App 要求 LLM 返回 JSON plan，然后用确定性代码校验。
- provider 未配置、依赖缺失或远端失败时，应返回结构化错误。
