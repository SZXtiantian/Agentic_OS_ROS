<h1 align="center">Agentic OS ROS</h1>

<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="agentic_runtime_src/"><img src="https://img.shields.io/badge/runtime-real--only-2f6f5e" alt="Runtime real-only"></a>
  <a href="ros2_bridge_src/"><img src="https://img.shields.io/badge/ROS2-Humble-3b6ea8" alt="ROS2 Humble"></a>
  <a href="agentic_apps/"><img src="https://img.shields.io/badge/Agent%20Apps-no%20rclpy-bc5b45" alt="Agent Apps do not import rclpy"></a>
  <a href="agentic_runtime_src/docs/access_audit.md"><img src="https://img.shields.io/badge/safety-audit%20logged-7c5c9e" alt="Safety and audit"></a>
</p>

<p align="center">
  <img src="assets/agentic-os-ros-concept.png" alt="Agentic OS ROS concept image" width="880">
</p>

**Agentic OS ROS** is an Agentic Runtime / Agentic OS source tree that runs above ROS2. It is not a normal ROS2 application, an LLM wrapper, or a fork of ROS2, Nav2, or MoveIt. Its purpose is to expose high-level, permissioned, safe, and auditable robot capabilities to Agent Apps while leaving realtime control to ROS2 controllers, Nav2, MoveIt, and vendor drivers.

Agent Apps do not touch `/cmd_vel`, `/scan`, `/odom`, `/tf`, Nav2 actions, or MoveIt actions directly. Every dangerous action must pass through Runtime permission checks, resource locks, safety guards, and audit logs before an AgenticOS-owned ROS2 Bridge / HAL adapts the request to ROS2.

---

## What This Project Provides

- **Agentic Runtime / Kernel**: core implementation for syscall lifecycles, scheduling, memory, context, storage, tools, skills, permissions, and audit.
- **Agentic SDK**: high-level APIs for Agent Apps, such as `ctx.robot.navigate_to(place)` and `ctx.memory.remember(key, value)`.
- **Robot Capability Layer**: maps task-level capabilities to permissions, resources, safety policy, and concrete bridge backends.
- **ROS2 Bridge Packages**: the only AgenticOS adapter layer allowed to import `rclpy`; it connects to ROS2 services, actions, topics, Nav2, MoveIt, or vendor drivers.
- **Agent App examples and templates**: includes `hello_world_agent`, `color_block_grasper_agent`, `robot_photographer_agent`, and the copyable `app_template`.
- **Real-only validation path**: production paths do not fabricate simulated success. Missing real dependencies return stable error codes such as `ROS_BRIDGE_UNAVAILABLE`, `LLM_PROVIDER_UNCONFIGURED`, or `UNVERIFIED_REAL_DEPENDENCY`.

---

## Current Robot Capability Path

The active real-robot manipulation path is the native `color_block_grasper_agent`.
It plans through the Runtime-owned LLM facade when required, validates policy in
the Agent App, and then calls high-level skills owned by Agentic Runtime:

- `perception.center_color_block` aligns the target block through the ROS2 bridge before grasp planning.
- `perception.detect_color_block` records pre-pick evidence and depth-backed target metadata.
- `manipulation.pick_color_block` executes the guarded arm/gripper sequence through bridge actions.
- `perception.verify_held_color_block` verifies post-pick evidence with ROI, size, position, and depth-delta checks.
- `manipulation.place_color_block` and `manipulation.open_gripper` complete the allowlisted place flow.

These capabilities remain real-only: if camera frames, depth data, servo bridge
subscribers, LLM configuration, or operator permissions are unavailable, the
runtime returns structured errors instead of fabricating success.

---

## Architecture

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Permission Checks / Resource Locks / Safety Guards / Audit Logs
  -> Robot Capability Layer
  -> AgenticOS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

Boundary rules:

- Agent Apps and Runtime code must not import `rclpy`.
- Agent Apps must not publish `/cmd_vel`.
- Agent Apps must not subscribe to `/scan`, `/odom`, or `/tf` directly.
- Agent Apps must not call Nav2 or MoveIt actions directly.
- Only ROS2 bridge packages under `ros2_bridge_src/*` may import `rclpy`.
- LLM / Agent logic must never perform realtime closed-loop control.
- `/home/ubuntu/ros2_ws/src` is reserved for traditional robot ROS2 application packages.
- `/opt/agentic` is the installed AgenticOS system root for bridge profiles, installed runtime code, skills, audit logs, runtime logs, and mutable state.

---

## Foundation API Surface

Agent Apps use robot and system capabilities only through high-level context APIs:

```python
ctx.robot.get_state()
ctx.robot.navigate_to(place)
ctx.robot.inspect_area(place)
ctx.robot.stop()
ctx.world.resolve_place(name)
ctx.memory.remember(key, value)
ctx.memory.recall(key)
ctx.human.ask(question)
ctx.report.say(message)
```

---

## Repository Layout

| Path | Responsibility |
| --- | --- |
| `agentic_runtime_src/` | Runtime, Kernel, SDK, syscalls, scheduler, permissions, audit, LLM facade, skill manifests, configs, scripts, tests, and documentation |
| `agentic_apps/` | Agent App examples and templates; new Agent Apps should start from `agentic_apps/app_template` |
| `ros2_bridge_src/` | AgenticOS-owned ROS2 bridge / HAL packages; this is the only source area in this repository where `rclpy` is allowed |
| `robot_descriptions/` | Robot descriptions, URDF / xacro files, meshes, and RViz resources |
| `scripts/` | Workspace-level static checks and test entrypoints |

---

## Quick Start

Install Runtime development dependencies and run unit tests:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
PYTHONPATH=. pytest -q
```

Run workspace static guards and foundation tests:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_agentic_app_tutorials.sh
```

Install into the AgenticOS system root:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
scripts/install_to_opt_agentic.sh
```

Build ROS2 bridge packages. This script targets the deployment workspace at `/home/ubuntu/agentic_ws`:

```bash
cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
scripts/build_robot_bridge.sh
```

Run real robot entrypoints:

```bash
/opt/agentic/bin/agentic --real --json "take a workspace photo"
/opt/agentic/bin/agentic photo --real --json "take a photo"
AGENTIC_LLM_ENABLED=1 AGENTIC_LLM_REQUIRE=1 \
  /opt/agentic/bin/agentic --real --json --require-llm "take a workspace photo"
```

Real arm motion requires explicit authorization:

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
  /opt/agentic/bin/agentic --real --allow-arm-motion --yes --json \
  "capture center, left, right, and top photos, then verify differences"
```

---

## Native Agent App Development

Create a new app from the template:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
```

Recommended docs:

- `agentic_runtime_src/docs/agentic_app_developer_guide.md`
- `agentic_runtime_src/docs/tutorials/hello_world_agent.md`
- `agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md`
- `agentic_runtime_src/docs/architecture.md`
- `agentic_runtime_src/docs/runtime_real_only.md`
- `agentic_runtime_src/docs/errors.md`

---

## Real Integration Verification

Real dependency checks are explicit opt-in paths and must not be replaced by simulated success:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
scripts/verify_real_ros2.sh
scripts/verify_real_llm.sh
scripts/verify_real_human.sh
```

When real dependencies are not configured, these scripts should report `UNVERIFIED_REAL_DEPENDENCY` with a next action instead of reporting false success.

---

## Safety Rules

- Do not modify `/opt/ros/*`, ROS2 upstream source, Nav2 upstream source, MoveIt upstream source, or robot vendor driver source.
- Do not place Agentic Runtime inside ROS2 as a normal business node.
- Do not commit `/opt/agentic/var`, real photos, videos, audit logs, task logs, run outputs, or secrets.
- Do not write API keys into source, README files, logs, or test snapshots.
- Do not present Gazebo, RViz-only, or fake Nav2 paths as real robot acceptance.
