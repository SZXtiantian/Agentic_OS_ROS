# ctx.human.ask

`ask` 向人询问问题或请求确认。当前实现使用 Runtime human file queue，不自动回答。

## Signature

```python
async def ask(
    question: str,
    options: list[str] | None = None,
    timeout_s: int = 60,
    require_confirmation: bool = False,
) -> HumanAnswer
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `question` | `str` | required | 问题文本 |
| `options` | `list[str] \| None` | `None` | 可选答案 |
| `timeout_s` | `int` | `60` | 等待 operator response 的秒数 |
| `require_confirmation` | `bool` | `False` | 是否作为确认流程 |

## Returns

`HumanAnswer`

```python
answered: bool
answer: str
reason: str
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `human.ask` |
| 权限 | `human.ask` |
| Backend | Runtime human file queue |
| Access | required，resource type 为 `human` |
| Timeout | `60s` |

## Common Errors

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `HUMAN_BACKEND_UNAVAILABLE`
- `HUMAN_OPERATOR_TIMEOUT`
- `HUMAN_CANCELLED`

## Example

```python
answer = await ctx.human.ask(
    "导航失败，是否重试一次？",
    options=["重试", "取消任务"],
    timeout_s=30,
    require_confirmation=True,
)
```
