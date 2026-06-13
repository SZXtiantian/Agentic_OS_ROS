# AgenticOS ROS2 Handoff For Simulation Host

## Purpose

This repository is handed off so AgenticOS can be tested in a separate system
that has a real simulation stack. The previous host is now treated as a
real-robot test environment, so the fake Nav2/RViz-only simulation harness was
removed before publishing.

The simulation host should provide the lower ROS2/robot layer and keep the
AgenticOS upper layers unchanged.

## Repository Layout

```text
agentic_runtime_src/
  AgenticOS runtime, kernel source, skills, configs, tests, install scripts.

agentic_apps/
  Agent Apps. The main vertical app is inspection_agent.

ros2_bridge_src/
  AgenticOS-owned ROS2 bridge/HAL packages:
  - agentic_msgs
  - agentic_world_model
  - agentic_safety_guard
  - agentic_capability_bridge
  - agentic_app_runtime_bridge

robot_descriptions/rosorin_description/
  Robot description assets that may be useful for RViz or simulator setup.
```

## Non-Negotiable Boundaries

- Do not modify ROS2, Nav2, MoveIt, or vendor driver source.
- Do not make Agent Apps import `rclpy`.
- Do not make Agent Apps publish `/cmd_vel`.
- Do not make Agent Apps subscribe to `/scan`, `/odom`, or `/tf` directly.
- Do not make Agent Apps call Nav2 or MoveIt actions directly.
- Runtime and SDK must not import `rclpy`.
- Only packages under `ros2_bridge_src/` may import `rclpy`.
- Robot movement must go through permission checks, resource locks, safety
  guards, and audit logs.

## Expected Simulation Architecture

The simulator should sit below the AgenticOS bridge layer:

```text
inspection_agent
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> AgenticOS permission / resource / safety / audit
  -> ros2_bridge_src bridge packages
  -> simulated Nav2 / perception / robot controllers
  -> simulator
```

For navigation, the key contract is:

```text
AgenticOS NavigateToPlace action
  /agentic/robot/navigate_to_place

Bridge maps this to standard Nav2:
  /navigate_to_pose
```

The simulation system should provide a working `/navigate_to_pose` action
through Nav2, or a simulator-backed equivalent that behaves like Nav2.

## Bring-Up On The Simulation Host

Assume the repository is checked out at:

```bash
/home/ubuntu/Agentic_OS_ROS
```

Create or reuse workspaces:

```bash
mkdir -p /home/ubuntu/agentic_ws/src
mkdir -p /home/ubuntu/agentic_ws/ros2_bridge_src
mkdir -p /home/ubuntu/ros2_ws/src
```

Copy or symlink source trees:

```bash
ln -s /home/ubuntu/Agentic_OS_ROS/agentic_runtime_src \
  /home/ubuntu/agentic_ws/src/agentic_runtime_src

for app in /home/ubuntu/Agentic_OS_ROS/agentic_apps/*; do
  ln -s "$app" /home/ubuntu/agentic_ws/src/
done

for pkg in /home/ubuntu/Agentic_OS_ROS/ros2_bridge_src/*; do
  ln -s "$pkg" /home/ubuntu/agentic_ws/ros2_bridge_src/
done

ln -s /home/ubuntu/Agentic_OS_ROS/robot_descriptions/rosorin_description \
  /home/ubuntu/ros2_ws/src/rosorin_description
```

Install AgenticOS into `/opt/agentic`:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

Build AgenticOS bridge packages:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_robot_bridge.sh
```

## Runtime Configuration

For a simulator-backed ROS2 stack, use the real-robot profile because the
simulator should expose real ROS2/Nav2 interfaces:

```bash
export AGENTIC_RUNTIME_CONFIG=/opt/agentic/etc/agentic_robot.yaml
```

The profile sets:

```yaml
ros_bridge_mode: cli
allow_mock_backends: false
```

That means Runtime uses ROS2 CLI transport and does not silently fall back to
mock robot backends.

## Start Order

1. Start the simulator and robot ROS2 stack.
2. Start localization/map/Nav2 in the simulator.
3. Verify Nav2:

   ```bash
   ros2 action list | grep /navigate_to_pose
   ros2 action info /navigate_to_pose
   ros2 topic list | grep -E '/tf|/odom'
   ```

4. Start AgenticOS bridge/HAL:

   ```bash
   /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_bridge.sh
   ```

5. Run the representative Agent App:

   ```bash
   /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_inspection.sh 厨房
   ```

Expected result:

```text
status=completed
success=true
```

## Evidence To Collect

After a run:

```bash
/opt/agentic/bin/agenticctl sessions --limit 5
/opt/agentic/bin/agenticctl audit --limit 12
```

For a valid navigation run, audit should show:

- `skill_name=robot.navigate_to`
- `backend=ros2_action`
- `permission_result=allowed`
- `resource_lock_result=locked`
- `safety_result=allowed`

## Important Config Files

- `agentic_runtime_src/configs/agentic_robot.yaml`
- `agentic_runtime_src/configs/places.yaml`
- `agentic_runtime_src/configs/safety.yaml`
- `agentic_runtime_src/skills/navigate_to.yaml`
- `ros2_bridge_src/agentic_capability_bridge/launch/robot_test.launch.py`

Update `places.yaml` so place names such as `厨房` map to poses that are valid
in the simulator's `map` frame.

## Current Validation From Source Host

Before handoff, the source host passed:

```text
source tests: 69 passed
installed /opt/agentic tests: 69 passed
real-robot bridge package build: passed
robot_test.launch.py short startup: passed
```

Physical/simulator navigation success is intentionally left for the simulation
host because this source host does not have the required simulation stack.

## What Not To Add Back

Do not reintroduce a fake Nav2 server inside AgenticOS runtime or Agent Apps.
If a simulator needs a mock, keep it below the ROS2/Nav2 layer as part of the
simulation environment. AgenticOS should continue to talk to stable robot
capability APIs and bridge contracts.

