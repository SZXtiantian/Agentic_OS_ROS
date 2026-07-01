# LLM API

`ctx.llm` 是 Runtime-owned LLM facade。Agent App 不创建 provider client，不读取 API key，也不直接依赖 OpenAI/LiteLLM/vLLM SDK。

## ctx.llm.chat_json

```python
async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int | None = None,
) -> LLMJSONResult
```

`LLMJSONResult` 字段：

```python
success: bool
plan: dict
error_code: str
reason: str
metadata: dict
```

注意：该 API 失败时返回 `LLMJSONResult(success=False, ...)`，不通过 `raise_for_result()` 抛 skill 异常。

常见错误：

- `LLMCHAT_UNAVAILABLE`
- `LLM_PROVIDER_UNCONFIGURED`
- `LLM_PROVIDER_REQUEST_FAILED`
- `LLM_RESPONSE_INVALID`

示例：

```python
plan = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=f"User task: {task_text}",
)
if not plan.success:
    return {"success": False, "error_code": plan.error_code, "reason": plan.reason}
```

LLM 只能生成计划或意图；实际机器人动作仍必须经过 SDK/Runtime。
