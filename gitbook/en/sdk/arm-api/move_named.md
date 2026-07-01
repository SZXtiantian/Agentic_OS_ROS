# ctx.arm.move_named

Execute an allowlisted named arm action. Apps must not send joint, torque, servo, or MoveIt commands directly.

## Signature

```python
async def move_named(name: str, timeout_s: int = 8) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | `str` | required | Named action; `home`/`init` map to `arm_home` |
| `timeout_s` | `int` | `8` | Timeout |

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `arm.move_named` |
| Permission | `arm.move.named` |
| Backend | ROS2 action `/agentic/arm/move_named` |
| Resource lock | `arm` |
| Safety | named action allowlist, workspace bounds, estop released |

## Example

```python
await ctx.arm.move_named("home", timeout_s=8)
```
