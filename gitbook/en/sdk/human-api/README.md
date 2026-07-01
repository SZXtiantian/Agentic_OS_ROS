# Human API

`ctx.human` asks a human operator or requests confirmation. The current implementation uses the Runtime human file queue and does not answer automatically.

## ctx.human.ask

```python
async def ask(
    question: str,
    options: list[str] | None = None,
    timeout_s: int = 60,
    require_confirmation: bool = False,
) -> HumanAnswer
```

`HumanAnswer` fields:

```python
answered: bool
answer: str
reason: str
```

Runtime contract:

| Item | Value |
| --- | --- |
| Skill | `human.ask` |
| Permission | `human.ask` |
| Backend | Runtime human file queue |
| Access | required, resource type `human` |
| Timeout | `60s` |

Common errors:

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `HUMAN_BACKEND_UNAVAILABLE`
- `HUMAN_OPERATOR_TIMEOUT`
- `HUMAN_CANCELLED`

Example:

```python
answer = await ctx.human.ask(
    "Navigation failed. Retry once?",
    options=["Retry", "Cancel"],
    timeout_s=30,
    require_confirmation=True,
)
if answer.answer != "Retry":
    await ctx.robot.stop(reason="operator_cancelled_retry")
```
