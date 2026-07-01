# Arm API

`ctx.arm` 用于读取机械臂状态和执行命名动作。Agent App 不直接调用 MoveIt 或机器人厂商机械臂驱动。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.arm.get_state()`](get_state.md) | 读取当前机械臂状态。 |
| [`ctx.arm.move_named(name, timeout_s=8)`](move_named.md) | 执行配置好的命名动作。 |
