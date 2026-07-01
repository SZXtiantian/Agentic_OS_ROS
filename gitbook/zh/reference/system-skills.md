# System Skills Reference

System skills 是 Runtime 真正执行的 capability contract。Agent App 通常通过 SDK 调用它们；专用应用可以在权限允许时通过 `ctx.kernel.skill.call(...)` 编排部分 system skill。

| Skill | SDK 入口 | 权限 | 资源锁 | Timeout |
| --- | --- | --- | --- | --- |
| `robot.get_state` | `ctx.robot.get_state()` | `robot.state.read` | 无 | `10s` |
| `robot.navigate_to` | `ctx.robot.navigate_to(...)` | `robot.move` | `base` | `120s` |
| `robot.inspect_area` | `ctx.robot.inspect_area(...)` | `perception.inspect` | `camera` | `60s` |
| `robot.stop` | `ctx.robot.stop(...)` | `robot.stop` | 无 | `10s` |
| `world.resolve_place` | `ctx.world.resolve_place(...)` | `world.read` | 无 | `10s` |
| `memory.remember` | `ctx.memory.remember(...)` | `memory.write` | 无 | `3s` |
| `memory.recall` | `ctx.memory.recall(...)` | `memory.read` | 无 | `3s` |
| `human.ask` | `ctx.human.ask(...)` | `human.ask` | 无 | `60s` |
| `report.say` | `ctx.report.say(...)` | `report.say` | 无 | `3s` |
| `perception.observe` | `ctx.perception.observe(...)` | `perception.observe` | `camera` | `10s` |
| `perception.capture_photo` | `ctx.perception.capture_photo(...)` | `perception.capture` | `camera` | `20s` |
| `arm.get_state` | `ctx.arm.get_state()` | `arm.state.read` | 无 | `5s` |
| `arm.move_named` | `ctx.arm.move_named(...)` | `arm.move.named` | `arm` | `8s` |
| `gripper.set` | `ctx.gripper.*` | `gripper.control` | `gripper` | `5s` |
| `storage.list_recent_photos` | `ctx.storage.list_recent_photos(...)` | `storage.read` | 无 | `5s` |
| `perception.detect_color_block` | `ctx.kernel.skill.call(...)` | `perception.detect.color_block` | `camera`, `color_block_detector` | `30s` |
| `perception.center_color_block` | `ctx.kernel.skill.call(...)` | `perception.center.color_block`, `arm.move.named` | `camera`, `arm`, `color_block_detector` | `30s` |
| `perception.verify_held_color_block` | `ctx.kernel.skill.call(...)` | `perception.verify.color_block_held` | `camera`, `color_block_detector` | `30s` |
| `manipulation.pick_color_block` | `ctx.kernel.skill.call(...)` | `manipulation.pick.color_block` | `arm`, `gripper`, `camera`, `manipulation_backend` | `60s` |
| `manipulation.place_color_block` | `ctx.kernel.skill.call(...)` | `manipulation.place.color_block` | `arm`, `gripper`, `manipulation_backend` | `60s` |
