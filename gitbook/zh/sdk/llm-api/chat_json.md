# ctx.llm.chat_json

`chat_json`: 请求 Runtime 调用 LLM，并返回 JSON object。

```python
async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int | None = None,
) -> LLMJSONResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `system_prompt` | `str` | required | 系统提示词。 |
| `user_prompt` | `str` | required | 用户提示词。 |
| `timeout_s` | `int \| None` | `None` | 预留参数；当前 SDK facade 不直接使用。 |

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
