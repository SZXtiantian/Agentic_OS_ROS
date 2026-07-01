# Human API

`ctx.human` 用于向人类操作员提问或请求确认。需要明确人工批准的动作应先通过这里确认。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.human.ask(question, options=None, timeout_s=60, require_confirmation=False)`](ask.md) | 向人提问并返回回答。 |
