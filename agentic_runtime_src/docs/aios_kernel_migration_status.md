# AIOS Kernel Migration Status

This is the AgenticOS system-root tracking document for the AIOS kernel migration.

Authoritative AgenticOS target:

```text
/opt/agentic
```

AgenticOS-owned hardware adapter paths:

```text
/opt/agentic/agentic_os/hardware
/opt/agentic/bridges/ros2
/opt/agentic/etc/bridge_profiles
```

Workspace boundaries:

```text
/home/ubuntu/agentic_ws
  Agentic App development workspace.

/home/ubuntu/agentic_ws/ros2_bridge_src
  ROS2/colcon source workspace for AgenticOS-owned bridge adapter packages.
  This is a build/source location for the AgenticOS hardware adapter layer, not
  an Agent App workspace. This is the only Agentic-owned area allowed to import
  rclpy.

/home/ubuntu/ros2_ws/src
  Robot ROS2 application workspace. Not AgenticOS kernel source.
```

Reference docs:

```text
/home/ubuntu/AIOS_TO_AGENTIC_OS_KERNEL_MIGRATION_TECHNICAL_PLAN.md
/home/ubuntu/CODEX_GOAL_PROMPT_AIOS_KERNEL_MIGRATION.md
/home/ubuntu/AGENTS.md
/opt/agentic/docs/filesystem_layout.md
/opt/agentic/docs/llm_provider_testing.md
```

Runtime LLM provider:

```text
provider: yunwu
config: /opt/agentic/etc/models.yaml
secret_env: AGENTIC_LLM_API_KEY or YUNWU_API_KEY
secret_file: /opt/agentic/etc/secrets/yunwu.env
```

`LLMChat` is owned by AgenticOS Runtime. Dispatcher and Agent Apps use the
Runtime facade only; they do not construct provider clients, parse model
configuration, or read API keys. Required LLM validation must set
`--require-llm` or `AGENTIC_LLM_REQUIRE=1`, which turns Dispatcher/App LLM
failure into structured errors instead of accepted rule fallback.

Goal command:

```text
/goal Build the Agentic OS kernel for ROS2 by migrating the existing AIOS kernel modules from /home/ubuntu/AIOS into /opt/agentic, the real AgenticOS system root. Treat /home/ubuntu/agentic_ws as the Agentic App workspace. Treat the ROS2 bridge as the AgenticOS-owned hardware / middleware adapter layer, analogous to a traditional OS HAL / driver layer; /home/ubuntu/agentic_ws/ros2_bridge_src is only the current ROS2/colcon bridge package source/build location. Follow /home/ubuntu/AIOS_TO_AGENTIC_OS_KERNEL_MIGRATION_TECHNICAL_PLAN.md as the execution plan. Implement ROS-safe counterparts for AIOS runtime service, syscall lifecycle, scheduler, memory provider, storage manager, tool manager, context manager, config refresh, app factory, session/status tracking, audit correlation, CLI commands, bridge profiles, adapter lifecycle, and bridge status/install concepts. Keep inspection_agent as the first representative app and make it run through the new /opt/agentic kernel/session path in mock mode. Preserve all architecture boundaries: no rclpy in /opt/agentic/lib/python3/agentic_runtime, SDK, or Agent Apps; only /home/ubuntu/agentic_ws/ros2_bridge_src bridge packages may import rclpy; robot movement must always pass permission checks, safety checks, resource locks, and audit logs. Work in small tested increments, validate the installed /opt/agentic commands, run static guard and pytest after each behavioral change, update docs and demo commands, and continue until the kernel architecture is complete. Real Nav2 wiring is a later phase unless the kernel migration is already complete, but the bridge/HAL layer belongs to the kernel architecture now.
```

Completed implementation:

```text
/opt/agentic/lib/python3/agentic_runtime/kernel_service
/opt/agentic/lib/python3/agentic_runtime/syscall
/opt/agentic/lib/python3/agentic_runtime/scheduler
/opt/agentic/lib/python3/agentic_runtime/session
/opt/agentic/lib/python3/agentic_runtime/memory
/opt/agentic/lib/python3/agentic_runtime/storage
/opt/agentic/lib/python3/agentic_runtime/tool_manager
/opt/agentic/lib/python3/agentic_runtime/context_manager
/opt/agentic/lib/python3/agentic_runtime/config_manager
/opt/agentic/lib/python3/agentic_runtime/app_factory
/opt/agentic/lib/python3/agentic_runtime/hardware_adapter
```

Phase checklist:

- [x] Phase -1 - Filesystem cleanup and duplicate runtime architecture guard
- [x] Phase 0 - Baseline audit and migration map
- [x] Phase 1 - Kernel service / agenticd
- [x] Phase 2 - Sessions and app submission
- [x] Phase 3 - Syscall lifecycle
- [x] Phase 4 - Scheduler
- [x] Phase 5 - Memory provider
- [x] Phase 6 - Storage manager
- [x] Phase 7 - Tool manager
- [x] Phase 8 - Context manager
- [x] Phase 9 - Config refresh
- [x] Phase 10 - CLI and docs
- [x] Phase 11 - AgenticOS hardware adapter / ROS2 bridge lifecycle

Installed validation commands:

```bash
/opt/agentic/bin/agenticctl status
/opt/agentic/bin/agentic-run inspection_agent --place 厨房 --mock
/opt/agentic/bin/agenticctl sessions --limit 5
/opt/agentic/bin/agenticctl session <session_id>
/opt/agentic/bin/agenticctl audit --limit 20
/opt/agentic/bin/agenticctl bridge status
cd /opt/agentic
source /opt/agentic/setup.bash
pytest -q tests
```

Transition-only compatibility checks, if the old source harness still exists:

```bash
cd /home/ubuntu/agentic_ws/src/agentic_runtime_src
python scripts/check_forbidden_imports.py
python scripts/check_filesystem_layout.py
pytest -q
```

Latest known passing acceptance session:

```text
session_id=sess_499bf4dae03a
app_id=inspection_agent
status=completed
```

Remaining deferred work:

- Replace mock bridge transport with real non-rclpy runtime-to-bridge transport.
- Generate concrete ROS2 bridge profiles per robot.
- Build and install ROS2 bridge packages from `/home/ubuntu/agentic_ws/ros2_bridge_src`.
- Wire Nav2 actions inside bridge packages only, keeping Runtime, SDK, and Apps free of `rclpy`.
- Add real robot safety integration tests after hardware or simulation profile selection.
