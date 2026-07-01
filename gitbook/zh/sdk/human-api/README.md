# Human API

`ctx.human` 用于向人询问或请求确认。当前实现使用 Runtime human file queue，不自动回答；没有 operator response 时会返回结构化超时。

## ctx.human.ask

```python
async def ask(
    question: str,
    options: list[str] | None = None,
    timeout_s: int = 60,
    require_confirmation: bool = False,
) -> HumanAnswer
```

`HumanAnswer` 字段：

```python
answered: bool
answer: str
reason: str
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `human.ask` |
| 权限 | `human.ask` |
| 后端 | Runtime human file queue |
| Access | required，resource type 为 `human` |
| Timeout | `60s` |

常见错误：

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `HUMAN_BACKEND_UNAVAILABLE`
- `HUMAN_OPERATOR_TIMEOUT`
- `HUMAN_CANCELLED`

示例：

```python
answer = await ctx.human.ask(
    "导航失败，是否重试一次？",
    options=["重试", "取消任务"],
    timeout_s=30,
    require_confirmation=True,
)
if answer.answer != "重试":
    await ctx.robot.stop(reason="operator_cancelled_retry")
```
