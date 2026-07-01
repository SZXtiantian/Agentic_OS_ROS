# ctx.gripper.set

执行 allowlist 中的夹爪命令。

## Signature

```python
async def set(
    command: str,
    force: str = "low",
    percentage: float | None = None,
    timeout_s: int = 5,
) -> SkillResult
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `gripper.set` |
| 权限 | `gripper.control` |
| 后端 | ROS2 service `/agentic/gripper/set` |
| 资源锁 | `gripper` |
| Safety | gripper allowlist、estop released |

## Example

```python
await ctx.gripper.set("open", force="low")
```
