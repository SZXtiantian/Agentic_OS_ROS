# Gripper API

`ctx.gripper` provides gripper open, close, and controlled commands. Commands are protected by allowlists, low-force policy, estop checks, and resource locks.

## APIs

| API | Skill | Permission | Resource lock | Return |
| --- | --- | --- | --- | --- |
| `ctx.gripper.open(timeout_s=5)` | `gripper.set` | `gripper.control` | `gripper` | `SkillResult` |
| `ctx.gripper.close(force="low", timeout_s=5)` | `gripper.set` | `gripper.control` | `gripper` | `SkillResult` |
| `ctx.gripper.set(command, force="low", percentage=None, timeout_s=5)` | `gripper.set` | `gripper.control` | `gripper` | `SkillResult` |

## ctx.gripper.open

```python
async def open(timeout_s: int = 5) -> SkillResult
```

Equivalent to:

```python
await ctx.gripper.set("open", force="low", timeout_s=timeout_s)
```

## ctx.gripper.close

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

`force="low"` maps to `"close_gripper_low_force"`.

## ctx.gripper.set

```python
async def set(
    command: str,
    force: str = "low",
    percentage: float | None = None,
    timeout_s: int = 5,
) -> SkillResult
```

Common errors:

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
