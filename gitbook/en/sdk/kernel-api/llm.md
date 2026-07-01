# ctx.kernel.llm

`ctx.kernel.llm` sends LLM system calls. Ordinary app structured JSON planning should use `ctx.llm.chat_json(...)` first.

All methods return `KernelSDKResult`.

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

| Parameter | Description |
| --- | --- |
| `messages` | Chat messages. |
| `prompt` | Completion prompt. |
| `texts` | Texts to embed. |
| `call_id` | Call ID to inspect or cancel. |
| `tools`, `selected_llms`, `response_format`, `params`, `timeout_s` | Optional LLM system call parameters. |

## Example

```python
result = await ctx.kernel.llm.chat(
    [{"role": "user", "content": "Plan a room inspection"}],
    response_format={"type": "json_object"},
    timeout_s=30,
)
```
