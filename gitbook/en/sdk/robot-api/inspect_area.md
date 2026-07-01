# ctx.robot.inspect_area

`inspect_area`: Inspect a named place or area and return an inspection result.

```python
async def inspect_area(place: str, timeout_s: int = 60) -> InspectionResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `place` | `str` | required | Place name to inspect. |
| `timeout_s` | `int` | `60` | Timeout for waiting for inspection to complete. |

## Returns

`InspectionResult`

```python
InspectionResult(
    success: bool,
    summary: str,
    objects: list,
    anomalies: list,
    evidence_path: str,
    evidence: dict,
)
```

## Example

```python
inspection = await ctx.robot.inspect_area("kitchen", timeout_s=60)
await ctx.report.say(inspection.summary)
```
