# LLM API

`ctx.llm` 请求 Runtime 执行结构化 LLM 调用。App 代码不读取 provider secret，也不直接构造 provider client。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.llm.chat_json(system_prompt=..., user_prompt=..., timeout_s=None)`](chat_json.md) | 请求 Runtime 返回 JSON object。 |
