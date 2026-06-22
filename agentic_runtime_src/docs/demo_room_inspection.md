# Demo: Room Inspection

## Real Bridge Happy Path

User request:

```text
去厨房看看。
```

Runtime flow:

1. `world.resolve_place("厨房")`
2. `robot.get_state()`
3. `robot.navigate_to("厨房")`
4. `robot.inspect_area("厨房")`
5. `memory.remember("last_inspection", result)`
6. `report.say("厨房检查完成，未发现异常。")`

Command:

```bash
/opt/agentic/bin/agentic-run inspection_agent --place 厨房 --real
```

Expected summary:

```text
收到任务：准备去厨房检查。
厨房检查完成，未发现异常。
success=true
```

This path requires the real AgenticOS ROS2 bridge services and robot/Nav2 stack
to be available. The runtime does not provide a simulated success backend.

## Missing Bridge

If ROS2, the AgenticOS bridge service, or the robot backend is unavailable, the
same app must fail visibly instead of fabricating a navigation or inspection
result.

Expected summary:

```text
ROS_BRIDGE_UNAVAILABLE 或 ROS_SERVICE_UNAVAILABLE
success=false
```

The audit log and session context should include the same error code.

## Forbidden Zone

Forbidden-zone validation is owned by the real safety bridge. When the bridge is
available and rejects `楼梯`, the app returns:

```text
FORBIDDEN_ZONE
success=false
```

If the bridge is unavailable, the expected result is the bridge availability
error above, not a locally fabricated forbidden-zone decision.

## Missing Permission

A test App without `robot.move` calling `ctx.robot.navigate_to("厨房")` receives:

```text
PERMISSION_DENIED
```

The navigation backend is not called.

## Timeout

Timeouts must come from the runtime timeout path or from real ROS2 bridge/action
timeouts. `robot.navigate_to` returns `SKILL_TIMEOUT` or `ROS_ACTION_TIMEOUT`,
releases any held resource locks, and writes an audit record.

## Stop

`ctx.robot.stop(reason="manual_stop")` marks active tasks cancelled through Runtime and calls the safety stop backend. It writes a `robot.stop` audit record.

## Kernel Session Inspection

Runs create persisted sessions under `/opt/agentic/var/sessions`:

```bash
/opt/agentic/bin/agenticctl sessions --limit 5
/opt/agentic/bin/agenticctl session <session_id>
/opt/agentic/bin/agenticctl audit --limit 20
```

Bridge ownership and profile status are visible through:

```bash
/opt/agentic/bin/agenticctl bridge status
```

## ROS2 Bridge Build

The ROS2 adapter packages can be built independently:

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/agentic_ws
colcon --log-base log/ros2_bridge build \
  --base-paths ros2_bridge_src \
  --build-base build/ros2_bridge \
  --install-base install/ros2_bridge \
  --packages-select \
  agentic_msgs \
  agentic_world_model \
  agentic_safety_guard \
  agentic_capability_bridge \
  agentic_app_runtime_bridge
```

The Runtime no longer ships an offline ROS bridge simulator for success-path
tests. If ROS2, bridge services, or robot/Nav2 are unavailable, runtime calls
must fail fast with stable bridge error codes. For ROS2 testing, use the real
bridge profile and a robot/Nav2 stack rather than a local simulation harness.

## Nav2 Integration Notes

`agentic_capability_bridge/navigation_bridge_node` exposes:

```bash
ros2 run agentic_capability_bridge navigation_bridge_node --ros-args \
  -p mock_nav:=false \
  -p places_file:=/opt/agentic/etc/places.yaml \
  -p nav2_action_name:=/navigate_to_pose
```

Run it only after:

1. Robot bringup is running.
2. Nav2 is running.
3. A map is loaded.
4. The robot is localized.
5. `configs/places.yaml` poses are valid in the `map` frame.

The MVP code keeps the Nav2 import isolated inside the ROS2 bridge package. Runtime and Agent Apps remain free of ROS2 client imports.
