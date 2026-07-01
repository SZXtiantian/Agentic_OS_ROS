# Kernel Modules

This section is organized by source directory under `agentic_runtime_src/agentic_os/kernel`. "App-facing entry" means a stable SDK method, system skill, or syscall facade that an Agent App may depend on. Runtime manager classes are not Agent App APIs.

| Kernel Directory | App-Facing Entry | Status |
| --- | --- | --- |
| [`access`](access.md) | `ctx.kernel.access.*`, plus automatic access/intervention in skill calls | Available advanced API |
| [`agent`](agent.md) | No direct App API yet | Runtime-internal lifecycle, to be expanded |
| [`capability`](capability.md) | manifest, system skill contracts, Runtime capability preflight | Indirect use |
| [`context`](context.md) | `ctx.kernel.context.*` | Available advanced API |
| [`device_arbitration`](device_arbitration.md) | No direct App API yet | Runtime-internal resource arbitration, to be expanded |
| [`hooks`](hooks.md) | No direct App API yet | Runtime-internal events, queues, and metrics hooks |
| [`human`](human.md) | `ctx.human.ask(...)`, `human.ask` system skill | Available App API |
| [`llm_core`](llm_core.md) | `ctx.llm.chat_json(...)`, `ctx.kernel.llm.*` | Available App API |
| [`memory`](memory.md) | `ctx.memory.*`, `ctx.kernel.memory.*` | Available App API |
| [`model_library`](model_library.md) | No direct App API yet | Model management contract, to be expanded |
| [`perception`](perception.md) | `ctx.perception.*`, perception system skills | Available App API |
| [`scheduler`](scheduler.md) | No direct App API yet | Runtime-internal scheduling, to be expanded |
| [`skill_library`](skill_library.md) | `ctx.kernel.skill.*`, system/app skill registry | Available advanced API |
| [`storage`](storage.md) | `ctx.storage.*`, `ctx.kernel.storage.*` | Available App API |
| [`system_call`](system_call.md) | `KernelSDKResult` returned by `ctx.kernel.*` | Syscall contract |
| [`tool`](tool.md) | `ctx.kernel.tool.*` | Non-robot tool API |
| [`world_model`](world_model.md) | `ctx.world.resolve_place(...)` | Available App API |

Developers should prefer high-level SDK methods such as `ctx.robot.get_state()`, `ctx.memory.remember(...)`, and `ctx.human.ask(...)`. Use `ctx.kernel.*` only when the app needs lower-level Runtime capabilities.

Agent Apps should not import manager classes from `agentic_os.kernel.*`, and must not bypass skills/runtime to call ROS2, Nav2, MoveIt, or hardware drivers.
