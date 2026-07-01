# LLM API

`ctx.llm` asks Runtime to run structured LLM calls. App code does not read provider secrets or construct provider clients.

## APIs

| API | Description |
| --- | --- |
| [`ctx.llm.chat_json(system_prompt=..., user_prompt=..., timeout_s=None)`](chat_json.md) | Ask Runtime for a JSON object result. |
