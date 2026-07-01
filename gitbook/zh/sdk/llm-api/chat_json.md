# ctx.llm.chat_json

`chat_json` 调用 Runtime-owned LLM facade，返回受约束 JSON plan。

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

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `system_prompt` | `str` | 系统提示词 |
| `user_prompt` | `str` | 用户输入或任务描述 |
| `timeout_s` | `int \| None` | 当前 facade 接收但不直接使用 |

## Returns

`LLMJSONResult`

```python
success: bool
plan: dict
error_code: str
reason: str
metadata: dict
```

该 API 失败时返回 `success=False`，不抛 `AgenticRuntimeError`。

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
