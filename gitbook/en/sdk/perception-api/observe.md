# ctx.perception.observe

`observe`: Observe a target area and return summary, object, and evidence information.

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `target` | `str` | `"workspace"` | Target area to observe. |
| `timeout_s` | `int` | `10` | Timeout for waiting for observation to complete. |

## Returns

`ObservationResult`

```python
ObservationResult(
    success: bool,
    summary: str,
    objects: list,
    evidence_path: str,
    evidence: dict,
)
```

## Example

```python
observation = await ctx.perception.observe(target="workspace", timeout_s=10)
await ctx.report.say(observation.summary)
```
