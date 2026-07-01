# Agentic OS Docs

Agentic OS exposes high-level, permissioned, safe, auditable robot capabilities to Agent Apps. This documentation is organized for GitBook as a developer portal: overview first, Agent App workflow next, then SDK namespaces, kernel module references, and capability reference material.

Choose a language:

- [中文文档](zh/README.md)
- [English Docs](en/README.md)

The API reference is intentionally organized around `AgentContext` namespaces:

- `ctx.robot`
- `ctx.world`
- `ctx.memory`
- `ctx.human`
- `ctx.report`
- `ctx.llm`
- `ctx.perception`
- `ctx.arm`
- `ctx.gripper`
- `ctx.storage`
- `ctx.kernel`

Kernel internals are also documented by source module under `agentic_runtime_src/agentic_os/kernel`, so developers can map app-facing APIs back to the Runtime implementation boundary.

Agent Apps must not import ROS2 libraries, publish robot topics, call Nav2 or MoveIt directly, or perform realtime closed-loop control. Robot actions go through Agentic Runtime permission checks, access/intervention, resource locks, safety guards, and audit logs.
