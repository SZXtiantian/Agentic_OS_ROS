# Kernel Hooks

This package provides AIOS-style module queues without importing AIOS globals.

The explicit `KernelQueueStore` is preferred for runtime wiring and tests. Global helper functions exist only as a small compatibility layer for code that expects AIOS-like queue access.

Robot lanes are separated from generic tools:

- `robot_motion` is for serialized dangerous motion work.
- `robot_sensor` is for sensing/perception work.
- generic `tool` must not expose robot, arm, gripper, perception, ROS2, Nav2, MoveIt, or direct velocity-command capabilities.
