# ctx.robot.navigate_to

Navigate the robot to a registered place. Apps pass a place name, not velocity commands, trajectories, Nav2 goals, or low-level coordinates.

## Signature

```python
async def navigate_to(place: str, timeout_s: int = 120) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `place` | `str` | required | Registered place name |
| `timeout_s` | `int` | `120` | Navigation timeout, range `1..300` |

## Returns

`SkillResult`. On success, `result.data` may include the bridge `result`.

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `robot.navigate_to` |
| Permission | `robot.move` |
| Backend | ROS2 action `/agentic/robot/navigate_to_place` |
| Bridge backend | Nav2 `/navigate_to_pose` |
| Resource lock | `base` |
| Safety | known place, localization, estop released, forbidden-zone check, max linear speed `0.5m/s` |
| Timeout | `120s` |

## Common Errors

- `PLACE_NOT_FOUND`
- `FORBIDDEN_ZONE`
- `ROBOT_NOT_LOCALIZED`
- `ESTOP_PRESSED`
- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_ACTION_UNAVAILABLE`
- `NAVIGATION_TIMEOUT`
- `NAVIGATION_FAILED`
- `SKILL_CANCELLED`

## Example

```python
place = await ctx.world.resolve_place("kitchen")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}

await ctx.robot.navigate_to(place.name, timeout_s=120)
```
