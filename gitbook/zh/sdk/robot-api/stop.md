# ctx.robot.stop

请求停止机器人或取消当前 session 的活跃任务。

## Signature

```python
async def stop(reason: str = "app_requested") -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `reason` | `str` | `"app_requested"` | 停止原因 |

## Returns

`SkillResult`

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `robot.stop` |
| 权限 | `robot.stop` |
| 后端 | ROS2 service `/agentic/robot/stop` |
| 资源锁 | 无，不被 `base` 锁阻塞 |
| Safety | high priority、bypass normal queue、audit required |
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
    await ctx.robot.navigate_to("厨房", timeout_s=120)
except Exception:
    await ctx.robot.stop(reason="navigation_exception")
    raise
```
