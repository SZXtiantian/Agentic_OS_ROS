# ctx.gripper.set

Execute an allowlisted gripper command.

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

| Item | Value |
| --- | --- |
| Skill | `gripper.set` |
| Permission | `gripper.control` |
| Backend | ROS2 service `/agentic/gripper/set` |
| Resource lock | `gripper` |
| Safety | gripper allowlist, estop released |

## Example

```python
await ctx.gripper.set("open", force="low")
```
