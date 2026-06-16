# Agentic OS ROS

This repository contains the current AgenticOS-over-ROS2 source tree used on the
real robot host.

AgenticOS is not a ROS2 business node, an LLM wrapper, or a fork of ROS2. It is
a runtime layer above ROS2 that exposes high-level, permissioned, safe, and
auditable robot capabilities to Agent Apps.

## Repository Layout

- `agentic_runtime_src/`: AgenticOS runtime, kernel contracts, SDK, dispatcher,
  natural-language gateway, task log, skill manifests, configs, scripts, tests,
  and documentation.
- `agentic_apps/`: Agent Apps and app templates. The current representative real
  robot app is `robot_photographer_agent`.
- `ros2_bridge_src/`: AgenticOS-owned ROS2 bridge/HAL packages. These are the
  only packages in this repository that may import `rclpy`.
- `docs/`: Workspace-level design notes and implementation plans.

## Architecture Boundary

Agent Apps and AgenticOS runtime code must not directly use ROS2 APIs. Robot
movement must flow through:

```text
User
  -> Natural Language Gateway
  -> Dispatcher Agent
  -> selected Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> permission checks / resource locks / safety checks / audit
  -> ROS2 bridge / HAL
  -> ROS2
  -> robot hardware
```

Only bridge packages under `ros2_bridge_src/` may import `rclpy`.

## Current Real-Robot Demo

`agentic_apps/robot_photographer_agent` is an AIOS-compatible and
AgenticOS-safe Agent App for real robot photography. It supports:

- single workspace photo
- recent photos
- status and stop
- controlled named arm poses for multi-angle photo capture
- deterministic image-difference verification

Real arm motion is gated by Runtime policy and requires:

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1
```

and explicit CLI flags such as `--allow-arm-motion --yes`.

## Common Commands

Install/update the runtime into `/opt/agentic`:

```bash
cd agentic_runtime_src
scripts/install_to_opt_agentic.sh
```

Run static and unit tests:

```bash
cd agentic_runtime_src
python scripts/check_forbidden_imports.py
scripts/run_tests.sh
pytest ../agentic_apps/robot_photographer_agent/tests
```

Build AgenticOS ROS2 bridge packages:

```bash
cd agentic_runtime_src
scripts/build_robot_bridge.sh
```

Use the installed natural-language entrypoint:

```bash
/opt/agentic/bin/agentic --mock --json "拍一张照片"
/opt/agentic/bin/agentic --real --json "拍一张工作区照片"
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 /opt/agentic/bin/agentic --real --allow-arm-motion --yes --json "从中间、左边、右边、上面拍照并验证差异"
```

## Safety Notes

- Do not commit `/opt/agentic/var`, app `storage/runs`, real photos, videos,
  audit logs, task logs, or secrets.
- Do not place API keys in source. LLM keys are loaded from
  `/opt/agentic/etc/secrets/yunwu.env` or `AGENTIC_LLM_API_KEY`.
- Do not add Gazebo/gz/fake Nav2/RViz-only demos to this real robot workspace.

