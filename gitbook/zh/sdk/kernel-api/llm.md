# ctx.kernel.llm

`ctx.kernel.llm` 发送 LLM system calls。普通 App 的结构化 JSON 规划优先使用 `ctx.llm.chat_json(...)`。

所有方法返回 `KernelSDKResult`。

## APIs

| API | System Call |
| --- | --- |
| `chat(messages, **kwargs)` | `LLMQuery(operation_type="llm_chat")` |
| `complete(prompt, **kwargs)` | `LLMQuery(operation_type="llm_complete")` |
| `embed(texts, **kwargs)` | `LLMQuery(operation_type="llm_embed")` |
| `status(call_id="", **kwargs)` | `LLMQuery(operation_type="llm_status")` |
| `cancel(call_id="", **kwargs)` | `LLMQuery(operation_type="llm_cancel")` |

## Signatures

```python
async def chat(messages: list[dict], **kwargs) -> KernelSDKResult
async def complete(prompt: str, **kwargs) -> KernelSDKResult
async def embed(texts, **kwargs) -> KernelSDKResult
async def status(call_id: str = "", **kwargs) -> KernelSDKResult
async def cancel(call_id: str = "", **kwargs) -> KernelSDKResult
```

## Parameters

| 参数 | 说明 |
| --- | --- |
| `messages` | Chat messages。 |
| `prompt` | Completion prompt。 |
| `texts` | 要 embedding 的文本。 |
| `call_id` | 要查询或取消的调用 ID。 |
| `tools`, `selected_llms`, `response_format`, `params`, `timeout_s` | 可选 LLM system call 参数。 |

## Example

```python
result = await ctx.kernel.llm.chat(
    [{"role": "user", "content": "Plan a room inspection"}],
    response_format={"type": "json_object"},
    timeout_s=30,
)
```
