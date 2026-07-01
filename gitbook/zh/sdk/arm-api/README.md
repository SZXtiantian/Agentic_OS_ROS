# Arm API

`ctx.arm` 提供机械臂状态读取和 allowlist 命名动作。应用不能直接下发关节、力矩、servo 或 MoveIt action。

## APIs

| API | Skill | 权限 | 资源锁 | 返回 |
| --- | --- | --- | --- | --- |
| `ctx.arm.get_state()` | `arm.get_state` | `arm.state.read` | 无 | `ArmState` |
| `ctx.arm.move_named(name, timeout_s=8)` | `arm.move_named` | `arm.move.named` | `arm` | `SkillResult` |

## ctx.arm.get_state

```python
async def get_state() -> ArmState
```

`ArmState` 字段：

```python
readiness: str
active_action: str
is_moving: bool
gripper_ready: bool
stop_available: bool
state: dict
```

## ctx.arm.move_named

```python
async def move_named(name: str, timeout_s: int = 8) -> SkillResult
```

`"home"` 和 `"init"` 会映射为 `"arm_home"`。动作必须在 `safety.yaml` 的 named action allowlist 中。

常见错误：

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_ACTION_UNAVAILABLE`
- `SKILL_TIMEOUT`
