<h1 align="center">Agentic OS ROS</h1>

<p align="center">
  <a href="README.md">English</a> | <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <a href="agentic_runtime_src/"><img src="https://img.shields.io/badge/runtime-real--only-2f6f5e" alt="Runtime real-only"></a>
  <a href="ros2_bridge_src/"><img src="https://img.shields.io/badge/ROS2-Humble-3b6ea8" alt="ROS2 Humble"></a>
  <a href="agentic_apps/"><img src="https://img.shields.io/badge/Agent%20Apps-no%20rclpy-bc5b45" alt="Agent Apps do not import rclpy"></a>
  <a href="agentic_runtime_src/docs/access_audit.md"><img src="https://img.shields.io/badge/safety-audit%20logged-7c5c9e" alt="Safety and audit"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-4f6f9f" alt="Apache 2.0 license"></a>
</p>

<p align="center">
  <img src="assets/agentic-os-ros-concept.png" alt="Agentic OS ROS concept image" width="880">
</p>

**Agentic OS ROS** is an Agentic Runtime / Agentic OS project running above ROS2. It provides a runtime boundary where Agent Apps can request high-level robot capabilities while safety, permissions, lifecycle control, and audit remain owned by the Agentic Runtime.

---

## What This Project Provides

- **Agentic Runtime / Kernel**: runtime services for permissions, scheduling, memory, context, storage, skills, and audit.
- **Agentic SDK**: high-level APIs for Agent Apps.
- **Robot Capability Layer**: policy-aware capability dispatch for robot tasks.
- **Environment-Aware DAG Scheduler**: explicit kernel policy
  `env_aware_priority_dag` for global TaskGraph scheduling, fact reuse,
  resource leases, lifecycle integration, audit, and debug export.
- **ROS2 Bridge Packages**: AgenticOS-owned adapters between the Runtime and ROS2.
- **Agent App templates and examples**: starter structure for building native Agent Apps.

---

## Architecture Boundary

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Robot Capability Layer
  -> AgenticOS ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

The key boundary is simple: Agent Apps and Runtime code stay above ROS2; ROS2-specific code belongs in AgenticOS-owned bridge packages.

---

## Repository Layout

| Path | Responsibility |
| --- | --- |
| `agentic_runtime_src/` | Runtime, Kernel, SDK, configs, scripts, tests, and documentation |
| `agentic_apps/` | Agent App templates and examples |
| `ros2_bridge_src/` | AgenticOS-owned ROS2 bridge packages |
| `robot_descriptions/` | Robot descriptions and visualization assets |
| `scripts/` | Workspace-level checks and test entrypoints |
| `assets/` | README and documentation images |

---

## Quick Start

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
scripts/verify_no_fake_mock.sh
```

For Runtime development:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
PYTHONPATH=. pytest -q
```

The environment-aware scheduler is documented in
[`agentic_runtime_src/docs/scheduler_environment_aware_dag.md`](agentic_runtime_src/docs/scheduler_environment_aware_dag.md).
Real scheduler LLM and capability verification scripts are opt-in and return
`UNVERIFIED_REAL_DEPENDENCY` until real providers, bridges, and capability
backends are configured. A missing scheduler capability bridge is reported as a
stable `ROS_SERVICE_UNAVAILABLE` or `ROS_ACTION_UNAVAILABLE`; the capability
verifier includes the required interface, visible ROS graph count, and command
in `NEXT_ACTION`, such as `required=/agentic/robot/get_state`,
`visible_services=0`, `command=ros2 service list`, and
`start_command=ros2 run agentic_capability_bridge state_bridge_node`. For that
read-only state service it also reports the bridge executable probe, for
example `bridge_executable=agentic_capability_bridge/state_bridge_node:available`
and `executable_command=ros2 pkg executables agentic_capability_bridge`. By
default the verifier does not start ROS nodes; set
`AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE=1` to temporarily start the real
read-only `state_bridge_node` for the duration of the check. Backend-unavailable
results include compact `ros_graph=` evidence with live node/topic/service/action
counts and configured camera/arm/gripper topic visibility, plus
`profile_dependencies=` from the selected robot profile so operators can see
candidate camera launch files, arm topics/services, and action-group file
presence, including `camera_backend=`, `arm_backend=`,
`gripper_backend=`, `camera_launch_files_present=`, and `next_backend_steps=`
action labels. `backend_step_hints=` maps those labels to non-executing operator
guidance, such as using the read-only state-bridge opt-in, starting the profile
camera launch, or performing operator-gated real arm/servo startup. The verifier
does not run those backend actions automatically.
The ROS discovery retry
window is controlled by
`AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS` and
`AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S`. Current
generic cup detection, pickup, held-verification, and delivery backends remain
real capability gaps; scheduler cup reuse must stay unavailable until those
real bridge/HAL paths exist.

---

## Safety Principles

- Keep Agentic Runtime separate from ROS2 application packages.
- Keep ROS2-specific imports inside bridge packages.
- Keep realtime control in ROS2 controllers, Nav2, MoveIt, or vendor drivers.
- Route robot actions through Runtime permissions, resource ownership, safety checks, and audit.
- Do not commit secrets, runtime state, audit logs, real captures, or generated run outputs.

---

## License

This project is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
