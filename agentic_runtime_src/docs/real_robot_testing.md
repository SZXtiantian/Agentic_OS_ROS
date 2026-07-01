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
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_system_skill_nodes.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/install_to_opt_agentic.sh
```

## Start Real Robot Bridge

Terminal 1: start robot bringup/Nav2 using the robot vendor or project launch
files.

Terminal 2: start AgenticOS bridge/HAL nodes:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_skills.sh
```

Optional environment variables:

```bash
ROBOT_ID=rosorin NAV2_ACTION_NAME=/navigate_to_pose \
  /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_skills.sh
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

## Run Robot Photographer With Real Camera

This validates the installed AgenticOS runtime in `/opt/agentic`, the
AgenticOS ROS2 bridge, and the real camera driver. It is not a mock test.
The real robot acceptance scripts must call `agentic photo --real`; if a real
bridge, camera, or arm backend is unavailable they fail with structured errors
instead of falling back to `--mock`.

Terminal 1: start or verify the AgenticOS bridge services:

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_robot_skills.sh
ros2 service list | grep -E '^/agentic/(perception/capture_photo|safety/check|robot/get_state)'
```

Terminal 2: start the real Aurora 930 camera driver and wait for a publisher
on `/depth_cam/rgb0/image_raw`:

```bash
source /opt/agentic/setup.bash
export need_compile=False
export DEPTH_CAMERA_TYPE=aurora
ros2 launch peripherals depth_camera.launch.py
```

In another terminal:

```bash
source /opt/agentic/setup.bash
ros2 topic info /depth_cam/rgb0/image_raw -v
timeout 8 ros2 topic echo --once /depth_cam/rgb0/image_raw sensor_msgs/msg/Image --field header
```

Expected signs of readiness:

```text
Publisher count: 1
Node name: aurora
frame_id: rgb_camera_link
```

Terminal 3: run the installed AgenticOS app path with real bridge mode:

```bash
source /opt/agentic/setup.bash
AGENTIC_PHOTO_EVIDENCE_ROOT=/opt/agentic/var/evidence/photos \
AGENTIC_ROBOT_PHOTOGRAPHER_STORAGE_ROOT=/opt/agentic/var/storage/robot_photographer_agent \
  /opt/agentic/bin/agentic photo --real --json 拍一张照片
```

Latest validation result on 2026-06-17:

```text
status: completed
success: true
perception_backend_status: CAPTURED
topic: /depth_cam/rgb0/image_raw
frame_id: rgb_camera_link
width: 640
height: 400
encoding: bgr8
audit_ids: audit_009543, audit_009544
```

Evidence from that run:

```text
/opt/agentic/var/evidence/photos/photo_20260617_135737_capture_4f697c881380.png
/opt/agentic/var/evidence/photos/photo_20260617_135737_capture_4f697c881380.json
/opt/agentic/var/storage/robot_photographer_agent/runs/sess_bbe925939d7a/photos/01_photo.png
/opt/agentic/var/storage/robot_photographer_agent/runs/sess_bbe925939d7a/metadata/01_photo.json
```

The app output image and raw evidence image were both verified as `640x400`
RGB PNG files.

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

Changing robots should require updating robot profiles, `places.yaml`, safety
limits, and robot bringup. It should not require changing Agent Apps, SDK,
Runtime, or Kernel APIs.
