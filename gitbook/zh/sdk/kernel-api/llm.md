# ctx.kernel.llm

Kernel LLM API 是更底层的 LLM syscall facade。普通 Agent App 的 JSON 规划优先使用 `ctx.llm.chat_json(...)`。

## Methods

```python
await ctx.kernel.llm.chat(messages: list[dict], **kwargs)
await ctx.kernel.llm.complete(prompt: str, **kwargs)
await ctx.kernel.llm.embed(texts, **kwargs)
await ctx.kernel.llm.status(call_id: str = "", **kwargs)
await ctx.kernel.llm.cancel(call_id: str = "", **kwargs)
```

## Returns

`KernelSDKResult`

## Example

```python
result = await ctx.kernel.llm.chat(
    [{"role": "user", "content": "Plan a room inspection"}],
    response_format={"type": "json_object"},
)
```
