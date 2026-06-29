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
scripts/verify_agentic_app_tutorials.sh
```

For Runtime development:

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
PYTHONPATH=. pytest -q
```

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
