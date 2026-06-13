# Embodied-Oriented Agentic OS Kernel

Importable AgenticOS kernel source namespace.

These modules are ROS2-safe ports of AIOS kernel concepts. They provide
system-call, scheduling, memory, storage, context, tool, model routing,
perception, device arbitration, and world-model primitives. Runtime service
code in `lib/python3/agentic_runtime` can adapt these modules to CLI/server
execution, but ROS2-specific imports must stay in bridge packages.

Canonical module names:

- `system_call`
- `capability`
- `skill_library`
- `memory`
- `model_library`
- `context`
- `tool`
- `storage`
- `scheduler`
- `perception`
- `device_arbitration`
- `world_model`
