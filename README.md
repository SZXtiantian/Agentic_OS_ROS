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
- `agentic_apps/`: Agent Apps and the canonical app template. Agentic App
  development starts by copying `agentic_apps/app_template`. 开发 Agentic App
  必须从 `agentic_apps/app_template` 复制开始。
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
- Runtime-owned LLM planning through `LLMChat`

LLM planning is an AgenticOS Runtime service. Agent Apps consume the injected
`llm_chat` interface and must not construct provider clients or read model
secrets directly. Normal operation may fall back to deterministic rule planning,
but real LLM acceptance uses `--require-llm` / `AGENTIC_LLM_REQUIRE=1` so the
Dispatcher and Robot Photographer cannot silently return `planner_mode:
rule_based`.

Real arm motion is gated by Runtime policy and requires:

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1
```

and explicit CLI flags such as `--allow-arm-motion --yes`.

Latest real-hardware validation on this workspace:

- Date: 2026-06-17
- Deployment root: `/opt/agentic`
- App: `robot_photographer_agent`
- Mode: real ROS2 bridge, real Aurora 930 camera
- Command: `/opt/agentic/bin/agentic photo --real --json 拍一张照片`
- Result: `success: true`, `status: completed`
- Captured topic: `/depth_cam/rgb0/image_raw`
- Captured frame: `640x400`, `bgr8`, `frame_id=rgb_camera_link`
- Raw evidence: `/opt/agentic/var/evidence/photos/photo_20260617_135737_capture_4f697c881380.png`
- App output: `/opt/agentic/var/storage/robot_photographer_agent/runs/sess_bbe925939d7a/photos/01_photo.png`
- Audit IDs: `audit_009543`, `audit_009544`

## Current Kernel Port Status

The AIOS-style kernel port has reached Phase 2 completion in this source tree.
The current kernel surface includes typed system call lifecycles, FIFO/RR
scheduler lanes, queue metrics and observability hooks, LLM provider routing
and batching, two-tier memory shells, LSFS-style storage surfaces, dynamic tool
loading, MCP lifecycle scaffolding, persistent access control, intervention
points, and robot-safe runtime bridge integration.

Primary progress docs:

- `agentic_runtime_src/docs/codex_kernel_phase2_progress.md`
- `agentic_runtime_src/docs/kernel/AIOS_KERNEL_PORTING_MAP.md`
- `agentic_runtime_src/docs/codex_kernel_port_progress.md`

The boundary remains unchanged: Runtime, kernel, SDK, and Agent Apps must not
import `rclpy`; ROS2-specific imports belong only in bridge packages under
`ros2_bridge_src/`.

## Real-Only Foundation Runtime

The runtime foundation is foundation-complete and real-only: production
CLI/API/config/schema do not
expose simulated runtime mode, and successful paths come from real providers,
backends, bridges, or services. Missing dependencies fail fast with stable
error codes and appear in status/audit instead of returning simulated success.

`KernelService.status()["providers"]` is the capability truth contract:
available modes must be implemented and tested, while unsupported/reserved
modes are listed separately. Current ROS bridge availability is `cli` only when
`ros2` CLI is present; service/action/topic/http/websocket bridge modes are not
advertised as available. LLM providers are available only when real config and
dependencies pass preflight; HF/local are reserved. Human operator flow uses
the real file queue and never auto-fills answers.

Primary contract docs:

- `agentic_runtime_src/docs/runtime_real_only.md`
- `agentic_runtime_src/docs/provider_contracts.md`
- `agentic_runtime_src/docs/kernel_syscalls.md`
- `agentic_runtime_src/docs/access_audit.md`
- `agentic_runtime_src/docs/real_integration.md`
- `agentic_runtime_src/docs/errors.md`

## Traditional ROS2 App Work

`/home/ubuntu/ros2_ws/src/color_block_grasper` is a traditional ROS2 RGB-D
color-block grasping application, not an Agent App. It is allowed to import
`rclpy` because it lives in the robot ROS2 application workspace. The design and
field notes are tracked here for project continuity:

- `docs/color_block_grasper_ros2_app_development.md`
- `docs/color_block_grasper_agentic_app_technical_plan.md`

Do not move this package into `agentic_apps/`, and do not make Agent Apps depend
on its direct ROS2 topics or servo commands.

## Native Agentic App Development

Start every native app from the template:

```bash
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
```

Developer docs:

- `agentic_runtime_src/docs/agentic_app_developer_guide.md`
- `agentic_runtime_src/docs/tutorials/hello_world_agent.md`
- `agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md`

Template-derived examples:

- `agentic_apps/hello_world_agent`
- `agentic_apps/color_block_grasper_agent`

Both tutorial examples plan natural-language tasks through the Agentic OS system
LLM facade (`ctx.llm.chat_json` -> `RuntimeServer.llm_chat`) before deterministic
validation and capability execution. They must not own provider clients or
return success when the required LLM path is unavailable.

## Common Commands

Install/update the runtime into `/opt/agentic`:

```bash
cd agentic_runtime_src
scripts/install_to_opt_agentic.sh
```

Run static and unit tests:

```bash
scripts/run_tests.sh
scripts/verify_agentic_app_tutorials.sh
PYTHONPATH=. pytest -q
```

Build AgenticOS ROS2 bridge packages:

```bash
cd agentic_runtime_src
scripts/build_robot_bridge.sh
```

Use the installed natural-language entrypoint:

```bash
/opt/agentic/bin/agentic --real --json "拍一张工作区照片"
/opt/agentic/bin/agentic photo --real --json "拍一张照片"
AGENTIC_LLM_ENABLED=1 AGENTIC_LLM_REQUIRE=1 /opt/agentic/bin/agentic --real --json --require-llm "拍一张工作区照片"
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 /opt/agentic/bin/agentic --real --allow-arm-motion --yes --json "从中间、左边、右边、上面拍照并验证差异"
```

## Safety Notes

- Do not commit `/opt/agentic/var`, app `storage/runs`, real photos, videos,
  audit logs, task logs, or secrets.
- Do not place API keys in source. LLM keys are loaded from
  `/opt/agentic/etc/secrets/yunwu.env` or `AGENTIC_LLM_API_KEY`.
- Do not add Gazebo/gz/fake Nav2/RViz-only demos to this real robot workspace.
