# AgenticOS Real Robot Deployment Taskbook

This taskbook is for the Codex instance responsible for deploying AgenticOS on
a real ROS2 robot. This host is treated as a real-robot test environment. Do
not add Gazebo, gz, fake Nav2, or RViz-only simulation harnesses here.

## Priority

The first real-robot demo should prioritize camera and manipulator capability,
not base navigation.

Reason:

- Camera + arm is safer to validate on a desk or test stand than autonomous
  base motion.
- It creates a stronger visual demo for a supervisor: the robot sees, reasons,
  and performs a bounded physical action.
- The current robot workspace already contains camera, servo, kinematics, and
  openclaw packages under `/home/ubuntu/ros2_ws/src`.
- Base navigation/Nav2 can remain supported, but it should be treated as the
  second deployment stage.

## Target Demo

Run one vertical AgenticOS demo on real hardware:

```text
User
  -> Agent App: camera_arm_inspection_agent or inspection_agent
  -> Agentic SDK
  -> /opt/agentic Runtime / Kernel
  -> Agentic-owned ROS2 bridge / HAL
  -> camera, perception, kinematics, servo/openclaw drivers
  -> robot camera and manipulator hardware
```

The preferred demo behavior is:

1. Start camera and manipulator bringup.
2. AgenticOS checks robot state, permissions, resource locks, and safety.
3. Camera bridge captures or observes one real image/depth/perception result.
4. Agent App reports what it sees.
5. Manipulation bridge performs one bounded safe action, for example:
   `arm_home`, `camera_up`, `open_gripper`, `close_gripper`, or a pre-approved
   small named pose.
6. AgenticOS writes session and audit evidence.

Do not start with free-form grasping or large arm trajectories. Those are later
steps after camera calibration, workspace limits, and stop behavior are proven.

## Architecture Boundary

Agent Apps must not import `rclpy`, publish servo topics, call kinematics
services, subscribe to image topics directly, or call MoveIt/driver APIs
directly.

All hardware access must go through:

```text
Agent App
  -> Agentic SDK high-level API
  -> Runtime / Kernel permission, lock, safety, audit
  -> ROS2 bridge package
  -> robot ROS2 camera / kinematics / servo / openclaw stack
```

Only packages under `/home/ubuntu/agentic_ws/ros2_bridge_src` may import
`rclpy`.

## Current State

Already present:

- Installed AgenticOS root: `/opt/agentic`
- Runtime source mirror: `/home/ubuntu/agentic_ws/src/agentic_runtime_src`
- Agent Apps workspace: `/home/ubuntu/agentic_ws/src`
- Agentic-owned ROS2 bridge source: `/home/ubuntu/agentic_ws/ros2_bridge_src`
- Real robot runtime config: `/opt/agentic/etc/agentic_robot.yaml`
- Existing bridge packages for world model, safety, state, navigation, and
  inspection
- Reserved SDK namespaces:
  `agentic_runtime/sdk/perception.py` and
  `agentic_runtime/sdk/manipulation.py`

Existing robot-side packages that are relevant for camera + arm:

- `/home/ubuntu/ros2_ws/src/peripherals/launch/depth_camera.launch.py`
- `/home/ubuntu/ros2_ws/src/peripherals/launch/usb_cam.launch.py`
- `/home/ubuntu/third_party/orbbec_ws` with Orbbec camera topics such as
  `/camera/color/image_raw`, `/camera/depth/image_raw`, and
  `/camera/depth/points`
- `/home/ubuntu/ros2_ws/src/driver/servo_controller`
- `/home/ubuntu/ros2_ws/src/driver/servo_controller_msgs`
- `/home/ubuntu/ros2_ws/src/driver/kinematics`
- `/home/ubuntu/ros2_ws/src/driver/kinematics_msgs`
- `/home/ubuntu/ros2_ws/src/openclaw_controller`
- `/home/ubuntu/ros2_ws/src/interfaces` with vision/object services and
  messages

What is real enough today:

- `inspection_bridge_node.py` exposes `/agentic/perception/inspect_area`, but
  it currently returns placeholder objects.
- The bridge build path and AgenticOS runtime installation path exist.
- Safety policy already treats inspection as a camera resource.

What is not real enough yet:

- There is no AgenticOS manipulation capability API yet.
- There are no AgenticOS ROS2 messages/services for arm named poses, gripper
  control, arm state, or camera observation.
- `inspection_bridge_node.py` does not consume a real camera image, detection
  topic, point cloud, or perception service.
- `state_bridge_node.py` does not report real arm/camera readiness.
- Safety guard does not yet enforce manipulator workspace limits, named-action
  allowlists, joint limits, or gripper limits.
- Stop behavior does not yet stop/cancel arm motion.
- No real-robot acceptance script exists for a camera + arm demo.

## Real Robot Prerequisites

Before moving hardware, Deployment Codex must inspect the ROS graph:

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 node list
ros2 topic list
ros2 service list
ros2 interface show servo_controller_msgs/msg/ServosPosition
ros2 interface show kinematics_msgs/srv/SetRobotPose
```

Candidate camera checks:

```bash
ros2 topic list | grep -E 'image_raw|camera_info|points|depth'
ros2 topic hz /camera/color/image_raw
ros2 topic hz /depth_cam/rgb0/image_raw
```

Candidate arm checks:

```bash
ros2 topic list | grep -E 'servo|joint|controller|claw'
ros2 service list | grep -E 'kinematics|pose|joint|claw'
ros2 launch openclaw_controller robot_base_control.launch.py
ros2 launch openclaw_controller claw_track_and_grab.launch.py
```

Those commands are probes, not guaranteed final launch commands. Use the actual
robot ROS graph discovered on the machine.

## Deployment Flow

1. Start robot camera and arm bringup outside AgenticOS.
2. Verify camera topics and safe arm/servo/kinematics interfaces manually.
3. Define a robot bridge profile, for example:
   `/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml`.
4. Add AgenticOS camera and manipulation contracts under `agentic_msgs`.
5. Add bridge nodes under `/home/ubuntu/agentic_ws/ros2_bridge_src`.
6. Add Runtime/SDK high-level APIs without importing `rclpy`.
7. Add safety checks, resource locks, structured errors, and audit records.
8. Run a read-only camera observation first.
9. Run one bounded arm action only after read-only checks pass.
10. Collect session and audit evidence.

## Required AgenticOS APIs

Deployment Codex should add the smallest useful high-level APIs. Suggested
shape:

```python
ctx.perception.observe(target="workspace")
ctx.arm.get_state()
ctx.arm.move_named("home")
ctx.arm.move_named("camera_up")
ctx.gripper.open()
ctx.gripper.close(force="low")
ctx.robot.stop()
```

These APIs must map to Runtime/Kernel capabilities and bridge calls. They must
not expose raw ROS topics or driver messages to Agent Apps.

## Implementation Tasks For Deployment Codex

### 1. Add Arm + Camera Bridge Profile

Create a source config and installed profile for the real robot.

It should include:

- robot id
- ROS domain id
- camera mode and topic names
- optional depth/point cloud topic names
- perception backend type
- arm backend type: `servo_controller`, `kinematics`, `openclaw_action_group`,
  or `moveit`
- allowed named arm poses/actions
- gripper open/close limits
- workspace bounds
- maximum arm duration
- stop/cancel backend
- evidence output directory under `/opt/agentic/var`

### 2. Add Agentic Messages For Camera + Arm

Add only the minimal contracts needed for the first demo.

Suggested services/actions:

- `Observe.srv`: target, request id, timeout -> success, summary, objects,
  evidence path/json
- `GetArmState.srv`: request -> readiness, active action, joint/pose metadata
- `MoveArmNamed.action` or `MoveArmNamed.srv`: named action, request id,
  timeout -> structured result
- `SetGripper.srv`: open/close or percentage -> structured result

Rebuild bridge messages after editing `agentic_msgs`.

### 3. Implement Camera Observation Bridge

Replace fake inspection behavior with real camera-backed observation.

Acceptable first implementation:

- Subscribe to a configured RGB topic.
- Record timestamp, frame id, width, height, encoding, and freshness.
- Optionally save one evidence image under `/opt/agentic/var/evidence`.
- If object detection is already running, normalize its latest result.
- If no image arrives, return `CAMERA_UNAVAILABLE` or
  `PERCEPTION_BACKEND_INCOMPLETE`.

Do not pretend fixed objects are real.

### 4. Implement Manipulation Bridge

Add an Agentic-owned bridge node that maps high-level named arm actions to the
robot's existing arm stack.

Acceptable first implementation:

- `arm_home`
- `camera_up`
- `open_gripper`
- `close_gripper_low_force`

Use the safest available backend discovered on the robot:

- existing openclaw action group, if available
- kinematics service for bounded named poses
- servo controller message for pre-approved positions
- MoveIt only if already configured and working

No Agent App may publish servo commands directly.

### 5. Add Manipulation Safety

Extend safety checks for:

- resource locks: `camera`, `arm`, `gripper`
- named action allowlist
- joint or pulse range limits
- workspace bounds
- timeout limits
- stop always allowed
- no base motion required for first demo

### 6. Implement Real Stop For Arm

`ctx.robot.stop()` or an equivalent Runtime stop path must stop/cancel active
arm actions as well as base actions.

For the first arm demo, this may mean canceling the active bridge action and
sending a configured safe hold/stop command through the bridge layer.

### 7. Add A Camera + Arm Agent App

Add a small Agent App such as `camera_arm_inspection_agent`.

Behavior:

- observe workspace with camera
- report evidence summary
- run one allowed named arm action
- optionally open/close gripper
- stop on error
- write human-readable report

### 8. Add Acceptance Script

Add a script such as:

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_camera_acceptance.sh
```

It must:

- run architecture guards
- verify AgenticOS status
- verify camera topics or return a truthful structured failure
- verify arm interfaces or return a truthful structured failure
- start bridge nodes if needed
- run read-only observation by default
- move the arm only when `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1`
- print latest session and audit logs

## Acceptance Criteria

The camera + arm deployment is not complete until:

- `/opt/agentic/bin/agenticctl status` passes.
- Static guards confirm only bridge packages import `rclpy`.
- Bridge packages build.
- Camera bridge reads a real camera topic or returns a truthful structured
  unavailable error.
- Inspection/perception no longer returns fixed fake objects as facts.
- Manipulation bridge can execute one allowed named action when explicitly
  enabled.
- Stop/cancel behavior for arm action is demonstrated or clearly reports the
  missing backend.
- Latest audit records show permission, resource lock, safety, backend, and
  result information for camera and arm operations.
- Base navigation is not required for the first real-robot demo.


