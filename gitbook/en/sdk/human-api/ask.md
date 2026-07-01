# ctx.human.ask

`ask` asks a human operator or requests confirmation. The current implementation uses the Runtime human file queue and does not auto-answer.

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

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `question` | `str` | required | Question text |
| `options` | `list[str] \| None` | `None` | Optional choices |
| `timeout_s` | `int` | `60` | Seconds to wait for operator response |
| `require_confirmation` | `bool` | `False` | Whether this is a confirmation flow |

## Returns

`HumanAnswer`

```python
answered: bool
answer: str
reason: str
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `human.ask` |
| Permission | `human.ask` |
| Backend | Runtime human file queue |
| Access | required, resource type `human` |
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
    "Navigation failed. Retry once?",
    options=["Retry", "Cancel"],
    timeout_s=30,
    require_confirmation=True,
)
```
