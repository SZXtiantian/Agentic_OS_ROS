# Arm API

`ctx.arm` reads arm state and runs allowlisted named actions. Apps must not send joints, torques, servo commands, or MoveIt actions directly.

## APIs

| API | Skill | Permission | Resource lock | Return |
| --- | --- | --- | --- | --- |
| `ctx.arm.get_state()` | `arm.get_state` | `arm.state.read` | None | `ArmState` |
| `ctx.arm.move_named(name, timeout_s=8)` | `arm.move_named` | `arm.move.named` | `arm` | `SkillResult` |

## ctx.arm.get_state

```python
async def get_state() -> ArmState
```

`ArmState` fields:

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

`"home"` and `"init"` are mapped to `"arm_home"`. The action must be allowlisted in `safety.yaml`.

Common errors:

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_ACTION_UNAVAILABLE`
- `SKILL_TIMEOUT`
