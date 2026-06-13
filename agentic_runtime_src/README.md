# Agentic OS for ROS2

This checkout now uses the deployment-oriented Agentic OS layout.

System installs:

```text
/opt/ros/humble
/opt/agentic
```

Development workspaces:

```text
/home/ubuntu/ros2_ws
/home/ubuntu/agentic_ws
```

Runtime source moved to:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src
```

Primary App moved to:

```text
/home/ubuntu/agentic_ws/src/inspection_agent
```

Compatibility symlinks:

```text
/home/ubuntu/agentic_runtime -> /home/ubuntu/agentic_ws/src/agentic_runtime_src
/home/ubuntu/agentic_apps -> /home/ubuntu/agentic_ws/src
```

Agentic OS is installed beside ROS2, not inside ROS2 and not as a normal ROS2 package.

It is not a normal ROS2 package, not a simple LLM wrapper, and not a fork of ROS2. The runtime exposes high-level, permissioned, safe, auditable robot capabilities to Agent Apps while leaving realtime robot control to ROS2 controllers, Nav2, MoveIt, and vendor drivers.

## Architecture Boundaries

- Do not modify `/opt/ros/*`, ROS2 upstream source, Nav2 source, MoveIt source, or vendor driver source.
- Agent Apps must not import `rclpy`.
- Agent Apps must not publish `/cmd_vel`.
- Agent Apps must not subscribe to `/scan`, `/odom`, or `/tf` directly.
- Agent Apps must not call Nav2 or MoveIt actions directly.
- Agentic Runtime must not import `rclpy`.
- Only ROS2 bridge packages under `/home/ubuntu/agentic_ws/ros2_bridge_src/*` may import `rclpy`.
- `/home/ubuntu/ros2_ws/src` is reserved for robot ROS2 application packages.
- LLM / Agent code must not perform realtime closed-loop control.
- All robot motion must pass through Agentic Runtime permission checks, resource locks, safety guards, and audit logs.

## MVP APIs

Agent Apps call only high-level APIs:

- `ctx.robot.get_state()`
- `ctx.robot.navigate_to(place)`
- `ctx.robot.inspect_area(place)`
- `ctx.robot.stop()`
- `ctx.world.resolve_place(name)`
- `ctx.memory.remember(key, value)`
- `ctx.memory.recall(key)`
- `ctx.human.ask(question)`
- `ctx.report.say(message)`

## Quick Start

```bash
source /opt/ros/humble/setup.bash
source /opt/agentic/setup.bash
source /home/ubuntu/agentic_ws/setup.bash

python /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/check_forbidden_imports.py

cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
python -m pip install -e ".[dev]"
pytest -q
python -m agentic_runtime.cli run-app inspection_agent --place 厨房 --mock
python -m agentic_runtime.cli status
```

Agentic ROS2 bridge packages live under `/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_*`. They are adapters, not the Agentic Runtime itself. The robot ROS2 workspace `/home/ubuntu/ros2_ws/src` should not contain Agentic source packages.
