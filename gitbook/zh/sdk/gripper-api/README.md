# Gripper API

`ctx.gripper` 通过 Runtime 控制夹爪。Agent App 不直接发布厂商夹爪控制话题。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.gripper.open(timeout_s=5)`](open.md) | 打开夹爪。 |
| [`ctx.gripper.close(force="low", timeout_s=5)`](close.md) | 关闭夹爪。 |
| [`ctx.gripper.set(command, force="low", percentage=None, timeout_s=5)`](set.md) | 发送受控夹爪命令。 |
