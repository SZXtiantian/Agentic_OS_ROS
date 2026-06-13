# AGENTS.md

## Project

This repository implements an Agentic OS / Agentic Runtime running above ROS2.

It is not a normal ROS2 application, not an LLM wrapper, and not a fork of ROS2.

The goal is to expose high-level, permissioned, safe, auditable robot capabilities to Agent Apps.

## Non-Negotiable Architecture Boundaries

- Do not modify `/opt/ros/*`, ROS2 upstream source, Nav2 upstream source, MoveIt upstream source, or robot vendor driver source.
- Do not place Agentic Runtime inside ROS2 as a normal business node.
- ROS2 bridge nodes are AgenticOS-owned hardware / middleware adapter components, analogous to an OS hardware abstraction / driver layer.
- In the current ROS2/colcon layout, ROS2 bridge node source packages are allowed only under `/home/ubuntu/agentic_ws/ros2_bridge_src/*`; this path is a bridge build/source workspace, not an Agent App workspace.
- Installed bridge artifacts, bridge profiles, generated adapter config, and bridge lifecycle ownership belong to `/opt/agentic`.
- `/home/ubuntu/ros2_ws/src` is reserved for robot ROS2 application packages.
- Agent Apps must not import `rclpy`.
- Agent Apps must not publish `/cmd_vel`.
- Agent Apps must not subscribe to `/scan`, `/odom`, or `/tf` directly.
- Agent Apps must not call Nav2 or MoveIt actions directly.
- Agentic Runtime must not import `rclpy`.
- Only ROS2 bridge packages under `/home/ubuntu/agentic_ws/ros2_bridge_src/*` may import `rclpy`.
- LLM / Agent logic must never perform realtime closed-loop control.
- All robot movement must go through Agentic Runtime permission checks, resource locks, safety guards, and audit logs.

## Layering

Expected layers:

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> AgenticOS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

## MVP APIs

Agent Apps may only call high-level APIs:

- `ctx.robot.get_state()`
- `ctx.robot.navigate_to(place)`
- `ctx.robot.inspect_area(place)`
- `ctx.robot.stop()`
- `ctx.world.resolve_place(name)`
- `ctx.memory.remember(key, value)`
- `ctx.memory.recall(key)`
- `ctx.human.ask(question)`
- `ctx.report.say(message)`

## Done Means

For every implementation task:

1. Code compiles.
2. Unit tests pass.
3. Integration or mock demo command is documented.
4. No forbidden ROS2 calls appear in Agent App code.
5. All dangerous robot actions go through permission checks, resource locks, safety guards, and audit logs.
6. Errors return structured error codes.
7. The task writes or updates tests when code behavior changes.
8. The final response lists changed files, commands run, test results, remaining risks, and next steps.

## Preferred Implementation Style

- Python for MVP Runtime and ROS2 bridge packages.
- `rclpy` only inside ROS2 bridge packages.
- No `rclpy` inside `agentic_runtime`, SDK, or Agent Apps.
- YAML / JSON Schema for manifests.
- SQLite for MVP memory.
- JSONL for MVP audit logs.
- Mock backends are acceptable where real robot integrations are unavailable.

## Build And Test

Common commands:

```bash
# ROS2 packages
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install

# Runtime
cd agentic_runtime
python -m pip install -e ".[dev]"
pytest -q

# Skeleton / static guard
scripts/run_tests.sh
```
