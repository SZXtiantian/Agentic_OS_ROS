# LLM API

`ctx.llm` is the Runtime-owned LLM facade. Agent Apps do not create provider clients, read API keys, or directly depend on OpenAI/LiteLLM/vLLM SDKs.

## ctx.llm.chat_json

```python
async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int | None = None,
) -> LLMJSONResult
```

`LLMJSONResult` fields:

```python
success: bool
plan: dict
error_code: str
reason: str
metadata: dict
```

This API returns `LLMJSONResult(success=False, ...)` on failure; it does not raise via `raise_for_result()`.

Common errors:

- `LLMCHAT_UNAVAILABLE`
- `LLM_PROVIDER_UNCONFIGURED`
- `LLM_PROVIDER_REQUEST_FAILED`
- `LLM_RESPONSE_INVALID`

Example:

```python
plan = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=f"User task: {task_text}",
)
if not plan.success:
    return {"success": False, "error_code": plan.error_code, "reason": plan.reason}
```

The LLM may generate a plan or intent only. Actual robot actions still go through SDK and Runtime checks.
