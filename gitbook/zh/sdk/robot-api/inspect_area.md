# ctx.robot.inspect_area

`inspect_area`: 检查一个地点或区域，并返回检查结果。

```python
async def inspect_area(place: str, timeout_s: int = 60) -> InspectionResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `place` | `str` | required | 要检查的地点名称。 |
| `timeout_s` | `int` | `60` | 等待检查完成的超时时间。 |

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
inspection = await ctx.robot.inspect_area("厨房", timeout_s=60)
await ctx.report.say(inspection.summary)
```
