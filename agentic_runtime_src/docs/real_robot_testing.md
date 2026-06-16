# AgenticOS Real Robot Testing Environment

This machine is treated as a real-robot test environment, not a simulation
environment. Do not start fake Nav2, Gazebo, or RViz-only simulation harnesses
from AgenticOS scripts on this host.

For the full deployment gap list, implementation tasks, and the goal prompt for
the deployment Codex, see `real_robot_deployment_taskbook.md`.

## Boundary

AgenticOS owns:

- Agent Apps under `/home/ubuntu/agentic_ws/src`
- Runtime and kernel under `/opt/agentic`
- ROS2 bridge/HAL packages under `/home/ubuntu/agentic_ws/ros2_bridge_src`

The robot stack owns:

- robot bringup
- localization
- map server
- real Nav2
- sensor drivers
- motor/actuator drivers

Agent Apps still must not import `rclpy`, publish `/cmd_vel`, read `/scan`,
read `/odom`, read `/tf`, or call Nav2 directly.

## Required Real Robot Services

Before running AgenticOS on the robot, the robot ROS2 stack must provide:

```bash
ros2 action list | grep /navigate_to_pose
ros2 topic list | grep -E '/tf|/odom'
```

The robot should also be localized and safe to accept Nav2 goals.

## Build

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_robot_bridge.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

## Start Real Robot Bridge

Terminal 1: start robot bringup/Nav2 using the robot vendor or project launch
files.

Terminal 2: start AgenticOS bridge/HAL nodes:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_bridge.sh
```

Optional environment variables:

```bash
ROBOT_ID=rosorin NAV2_ACTION_NAME=/navigate_to_pose \
  /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_bridge.sh
```

## Run Inspection App

Terminal 3:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_inspection.sh 厨房
```

Expected successful result:

```text
status=completed
success=true
```

## Evidence To Show

```bash
/opt/agentic/bin/agenticctl sessions --limit 5
/opt/agentic/bin/agenticctl audit --limit 12
```

For robot movement, audit records must show:

- `skill_name=robot.navigate_to`
- `backend=ros2_action`
- `permission_result=allowed`
- `resource_lock_result=locked`
- `safety_result=allowed`

## Real Robot Migration Rule

Changing robots should require updating bridge profiles, `places.yaml`, safety
limits, and robot bringup. It should not require changing Agent Apps, SDK,
Runtime, or Kernel APIs.
