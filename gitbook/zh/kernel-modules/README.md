# Kernel Modules

本节按照源码目录 `agentic_runtime_src/agentic_os/kernel` 组织 API。这里的“App 可用入口”指 Agent App 可以稳定依赖的 SDK、system skill 或 syscall facade；Runtime manager 内部类不是 App API。

| Kernel 目录 | App 可用入口 | 状态 |
| --- | --- | --- |
| [`access`](access.md) | `ctx.kernel.access.*`，以及 skill 调用中的自动 access/intervention | 已有进阶入口 |
| [`agent`](agent.md) | 暂无直接 App API | Runtime 内部生命周期管理，后续完善 |
| [`capability`](capability.md) | manifest、system skill contract、Runtime capability preflight | 间接使用 |
| [`context`](context.md) | `ctx.kernel.context.*` | 已有进阶入口 |
| [`device_arbitration`](device_arbitration.md) | 暂无直接 App API | Runtime 内部资源仲裁，后续完善 |
| [`hooks`](hooks.md) | 暂无直接 App API | Runtime 内部事件、队列、指标 hooks |
| [`human`](human.md) | `ctx.human.ask(...)`、`human.ask` system skill | 已有 App 入口 |
| [`llm_core`](llm_core.md) | `ctx.llm.chat_json(...)`、`ctx.kernel.llm.*` | 已有 App 入口 |
| [`memory`](memory.md) | `ctx.memory.*`、`ctx.kernel.memory.*` | 已有 App 入口 |
| [`model_library`](model_library.md) | 暂无直接 App API | 模型管理 contract，后续完善 |
| [`perception`](perception.md) | `ctx.perception.*`、perception system skills | 已有 App 入口 |
| [`scheduler`](scheduler.md) | 暂无直接 App API | Runtime 内部调度，后续完善 |
| [`skill_library`](skill_library.md) | `ctx.kernel.skill.*`、system/app skill registry | 已有进阶入口 |
| [`storage`](storage.md) | `ctx.storage.*`、`ctx.kernel.storage.*` | 已有 App 入口 |
| [`system_call`](system_call.md) | `ctx.kernel.*` 返回的 `KernelSDKResult` | syscall contract |
| [`tool`](tool.md) | `ctx.kernel.tool.*` | 非机器人工具入口 |
| [`world_model`](world_model.md) | `ctx.world.resolve_place(...)` | 已有 App 入口 |

开发者应该优先使用高层 SDK，例如 `ctx.robot.get_state()`、`ctx.memory.remember(...)`、`ctx.human.ask(...)`。只有当 App 确实需要更底层的 Runtime 能力时，才使用 `ctx.kernel.*`。

Agent App 不应该直接 import `agentic_os.kernel.*` 的 manager 类，也不应该绕过 skill/runtime 去调用 ROS2、Nav2、MoveIt 或硬件驱动。
