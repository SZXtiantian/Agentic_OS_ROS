# ctx.human.ask

`ask`: Ask a human operator a question and wait for an answer or confirmation.

```python
async def ask(
    question: str,
    options: list[str] | None = None,
    timeout_s: int = 60,
    require_confirmation: bool = False,
) -> HumanAnswer
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `question` | `str` | required | Question shown to the operator. |
| `options` | `list[str] \| None` | `None` | Optional answer choices. |
| `timeout_s` | `int` | `60` | Timeout for waiting for an answer. |
| `require_confirmation` | `bool` | `False` | Whether explicit confirmation is required. |

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
    "Can the robot start inspecting the kitchen?",
    options=["yes", "no"],
    timeout_s=60,
    require_confirmation=True,
)
```
