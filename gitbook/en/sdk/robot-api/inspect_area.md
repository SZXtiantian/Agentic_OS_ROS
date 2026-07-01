# ctx.robot.inspect_area

Inspect a registered area and return a summary, objects, anomalies, and evidence metadata.

## Signature

```python
async def inspect_area(place: str, timeout_s: int = 60) -> InspectionResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `place` | `str` | required | Registered place name |
| `timeout_s` | `int` | `60` | Inspection timeout, range `1..120` |

## Returns

`InspectionResult`

```python
success: bool
summary: str
objects: list[str]
anomalies: list[str]
evidence_path: str
evidence: dict
error_code: str
reason: str
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `robot.inspect_area` |
| Permission | `perception.inspect` |
| Backend | ROS2 service `/agentic/perception/inspect_area` |
| Resource lock | `camera` |
| Safety | known place, cancellable, runtime timeout margin `5s` |
| Timeout | `60s` |

## Common Errors

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `INSPECTION_FAILED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `SKILL_TIMEOUT`

## Example

```python
inspection = await ctx.robot.inspect_area("kitchen", timeout_s=60)
await ctx.memory.remember("last_inspection", inspection.to_dict())
```
