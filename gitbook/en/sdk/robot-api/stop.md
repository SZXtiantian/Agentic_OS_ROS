# ctx.robot.stop

Request robot stop or cancel active work in the current session.

## Signature

```python
async def stop(reason: str = "app_requested") -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `reason` | `str` | `"app_requested"` | Stop reason |

## Returns

`SkillResult`

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `robot.stop` |
| Permission | `robot.stop` |
| Backend | ROS2 service `/agentic/robot/stop` |
| Resource lock | None; it is not blocked by the `base` lock |
| Safety | high priority, bypass normal queue, audit required |
| Timeout | `10s` |

## Common Errors

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `UNEXPECTED_ERROR`

## Example

```python
try:
    await ctx.robot.navigate_to("kitchen", timeout_s=120)
except Exception:
    await ctx.robot.stop(reason="navigation_exception")
    raise
```
