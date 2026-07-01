# ctx.robot.navigate_to

`navigate_to`: Navigate the robot to a named place.

```python
async def navigate_to(place: str, timeout_s: int = 120) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `place` | `str` | required | Place name. It should come from `ctx.world.resolve_place(...)` or an app-validated place name. |
| `timeout_s` | `int` | `120` | Timeout for waiting for navigation to complete. |

## Returns

`SkillResult`

## Example

```python
place = await ctx.world.resolve_place("kitchen")
result = await ctx.robot.navigate_to(place.name, timeout_s=120)
```
