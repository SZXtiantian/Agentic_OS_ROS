# ctx.kernel.llm

Kernel LLM API is the lower-level LLM syscall facade. Ordinary Agent App JSON planning should use `ctx.llm.chat_json(...)` first.

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
