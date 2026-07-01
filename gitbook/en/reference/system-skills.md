# System Skills Reference

System skills are the Runtime capability contracts. Agent Apps normally call them through SDK namespaces; specialized apps may orchestrate some skills through `ctx.kernel.skill.call(...)` when permissions allow.

System skills live under:

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

`SKILL.md` defines the contract only. The real backend is selected by `implementation`: `runtime_internal` points to Runtime-owned code, while `ros2_service`/`ros2_action` points to Agentic OS-owned bridges. When adding a Python-backed skill, put backend code in the same skill directory or clearly document backend ownership in the contract.

| Skill | SDK Entry | Permission | Resource Locks | Timeout |
| --- | --- | --- | --- | --- |
| `robot.get_state` | `ctx.robot.get_state()` | `robot.state.read` | None | `10s` |
| `robot.navigate_to` | `ctx.robot.navigate_to(...)` | `robot.move` | `base` | `120s` |
| `robot.inspect_area` | `ctx.robot.inspect_area(...)` | `perception.inspect` | `camera` | `60s` |
| `robot.stop` | `ctx.robot.stop(...)` | `robot.stop` | None | `10s` |
| `world.resolve_place` | `ctx.world.resolve_place(...)` | `world.read` | None | `10s` |
| `memory.remember` | `ctx.memory.remember(...)` | `memory.write` | None | `3s` |
| `memory.recall` | `ctx.memory.recall(...)` | `memory.read` | None | `3s` |
| `human.ask` | `ctx.human.ask(...)` | `human.ask` | None | `60s` |
| `report.say` | `ctx.report.say(...)` | `report.say` | None | `3s` |
| `perception.observe` | `ctx.perception.observe(...)` | `perception.observe` | `camera` | `10s` |
| `perception.capture_photo` | `ctx.perception.capture_photo(...)` | `perception.capture` | `camera` | `20s` |
| `arm.get_state` | `ctx.arm.get_state()` | `arm.state.read` | None | `5s` |
| `arm.move_named` | `ctx.arm.move_named(...)` | `arm.move.named` | `arm` | `8s` |
| `gripper.set` | `ctx.gripper.*` | `gripper.control` | `gripper` | `5s` |
| `storage.list_recent_photos` | `ctx.storage.list_recent_photos(...)` | `storage.read` | None | `5s` |
| `perception.detect_color_block` | `ctx.kernel.skill.call(...)` | `perception.detect.color_block` | `camera`, `color_block_detector` | `30s` |
| `perception.center_color_block` | `ctx.kernel.skill.call(...)` | `perception.center.color_block`, `arm.move.named` | `camera`, `arm`, `color_block_detector` | `30s` |
| `perception.verify_held_color_block` | `ctx.kernel.skill.call(...)` | `perception.verify.color_block_held` | `camera`, `color_block_detector` | `30s` |
| `manipulation.pick_color_block` | `ctx.kernel.skill.call(...)` | `manipulation.pick.color_block` | `arm`, `gripper`, `camera`, `manipulation_backend` | `60s` |
| `manipulation.place_color_block` | `ctx.kernel.skill.call(...)` | `manipulation.place.color_block` | `arm`, `gripper`, `manipulation_backend` | `60s` |

## Constraints

- Agent Apps must not call the ROS2 service/action behind a system skill directly.
- Robot actions must not be converted into generic tools.
- Real-device actions must keep permissions, resource locks, safety constraints, timeouts, and audit.
- App-private logic belongs in an app skill, such as `color_block_grasper_agent/skills/find_best_block`.
