# ctx.llm.chat_json

`chat_json` calls the Runtime-owned LLM facade and returns a constrained JSON plan.

## Signature

```python
async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int | None = None,
) -> LLMJSONResult
```

## Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `system_prompt` | `str` | System prompt |
| `user_prompt` | `str` | User input or task text |
| `timeout_s` | `int \| None` | Accepted by the facade but not directly used |

## Returns

`LLMJSONResult`

```python
success: bool
plan: dict
error_code: str
reason: str
metadata: dict
```

This API returns `success=False` on failure and does not raise `AgenticRuntimeError`.

## Common Errors

- `LLMCHAT_UNAVAILABLE`
- `LLM_PROVIDER_UNCONFIGURED`
- `LLM_PROVIDER_REQUEST_FAILED`
- `LLM_RESPONSE_INVALID`

## Example

```python
plan = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=f"User task: {task_text}",
)
if not plan.success:
    return {"success": False, "error_code": plan.error_code, "reason": plan.reason}
```
