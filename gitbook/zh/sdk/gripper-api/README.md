# Gripper API

`ctx.gripper` 提供夹爪打开、关闭和受控命令。夹爪命令受 allowlist、低力策略、急停和资源锁保护。

## APIs

| API | Skill | 权限 | 资源锁 | 返回 |
| --- | --- | --- | --- | --- |
| `ctx.gripper.open(timeout_s=5)` | `gripper.set` | `gripper.control` | `gripper` | `SkillResult` |
| `ctx.gripper.close(force="low", timeout_s=5)` | `gripper.set` | `gripper.control` | `gripper` | `SkillResult` |
| `ctx.gripper.set(command, force="low", percentage=None, timeout_s=5)` | `gripper.set` | `gripper.control` | `gripper` | `SkillResult` |

## ctx.gripper.open

```python
async def open(timeout_s: int = 5) -> SkillResult
```

等价于：

```python
await ctx.gripper.set("open", force="low", timeout_s=timeout_s)
```

## ctx.gripper.close

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

`force="low"` 会映射为 `"close_gripper_low_force"`。

## ctx.gripper.set

```python
async def set(
    command: str,
    force: str = "low",
    percentage: float | None = None,
    timeout_s: int = 5,
) -> SkillResult
```

常见错误：

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
