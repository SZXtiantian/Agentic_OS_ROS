# ctx.llm.chat_json

`chat_json`: Ask Runtime to call an LLM and return a JSON object.

```python
async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int | None = None,
) -> LLMJSONResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `system_prompt` | `str` | required | System prompt. |
| `user_prompt` | `str` | required | User prompt. |
| `timeout_s` | `int \| None` | `None` | Reserved parameter; the current SDK facade does not use it directly. |

## Returns

`LLMJSONResult`

```python
LLMJSONResult(
    success: bool,
    plan: dict = {},
    error_code: str = "",
    reason: str = "",
    metadata: dict = {},
)
```

## Example

```python
plan = await ctx.llm.chat_json(
    system_prompt="Return JSON only.",
    user_prompt="Plan a kitchen inspection.",
)
if not plan.success:
    return {"success": False, "error_code": plan.error_code}
```
