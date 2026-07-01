# ctx.arm.move_named

执行 allowlist 中的命名机械臂动作。应用不能直接下发关节、力矩、servo 或 MoveIt action。

## Signature

```python
async def move_named(name: str, timeout_s: int = 8) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | required | 命名动作；`home`/`init` 映射为 `arm_home` |
| `timeout_s` | `int` | `8` | 超时时间 |

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `arm.move_named` |
| 权限 | `arm.move.named` |
| 后端 | ROS2 action `/agentic/arm/move_named` |
| 资源锁 | `arm` |
| Safety | named action allowlist、workspace bounds、estop released |

## Example

```python
await ctx.arm.move_named("home", timeout_s=8)
```
