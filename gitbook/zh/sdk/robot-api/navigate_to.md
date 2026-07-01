# ctx.robot.navigate_to

导航机器人到已注册地点。应用传入地点名，不能传入速度、轨迹、Nav2 goal 或底层坐标控制。

## Signature

```python
async def navigate_to(place: str, timeout_s: int = 120) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `place` | `str` | required | 已注册地点名，例如 `"厨房"` |
| `timeout_s` | `int` | `120` | 导航超时，范围 `1..300` |

## Returns

`SkillResult`。成功时 `result.data` 可包含 bridge 返回的 `result`。

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `robot.navigate_to` |
| 权限 | `robot.move` |
| 后端 | ROS2 action `/agentic/robot/navigate_to_place` |
| Bridge backend | Nav2 `/navigate_to_pose` |
| 资源锁 | `base` |
| Safety | known place、本地化、急停释放、禁区检查、最大线速度 `0.5m/s` |
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
place = await ctx.world.resolve_place("厨房")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}

await ctx.robot.navigate_to(place.name, timeout_s=120)
```
