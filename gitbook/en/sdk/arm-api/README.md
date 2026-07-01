# Arm API

`ctx.arm` reads arm state and runs named arm motions. Agent Apps must not call MoveIt or robot vendor arm drivers directly.

## APIs

| API | Description |
| --- | --- |
| [`ctx.arm.get_state()`](get_state.md) | Read the current arm state. |
| [`ctx.arm.move_named(name, timeout_s=8)`](move_named.md) | Run a configured named arm motion. |
