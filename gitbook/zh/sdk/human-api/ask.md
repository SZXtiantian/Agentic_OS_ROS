# ctx.human.ask

`ask`: 向人类操作员提问，并等待回答或确认。

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
| `question` | `str` | required | 展示给操作员的问题。 |
| `options` | `list[str] \| None` | `None` | 可选回答列表。 |
| `timeout_s` | `int` | `60` | 等待回答的超时时间。 |
| `require_confirmation` | `bool` | `False` | 是否要求明确确认。 |

## Returns

`HumanAnswer`

```python
HumanAnswer(
    answered: bool,
    answer: str,
    reason: str = "",
)
```

## Example

```python
answer = await ctx.human.ask(
    "是否允许机器人开始检查厨房？",
    options=["yes", "no"],
    timeout_s=60,
    require_confirmation=True,
)
```
