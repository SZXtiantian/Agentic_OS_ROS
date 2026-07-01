# Gripper API

`ctx.gripper` controls the gripper through Runtime. Agent Apps must not publish vendor gripper control topics directly.

## APIs

| API | Description |
| --- | --- |
| [`ctx.gripper.open(timeout_s=5)`](open.md) | Open the gripper. |
| [`ctx.gripper.close(force="low", timeout_s=5)`](close.md) | Close the gripper. |
| [`ctx.gripper.set(command, force="low", percentage=None, timeout_s=5)`](set.md) | Send a controlled gripper command. |
