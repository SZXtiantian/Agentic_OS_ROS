# Hello World Agentic App

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

This tutorial builds `hello_world_agent`, a template-derived app that plans from
natural language through the Agentic OS Runtime LLM facade and then exercises
Kernel context, memory, storage, tool, skill, and report surfaces.

## Create

```bash
python scripts/create_agentic_app.py hello_world_agent \
  --description "Template-derived Agentic App that exercises context, memory, storage, tool, skill, and report surfaces."
```

The generated app keeps `README.md`, `app.yaml`, `main.py`,
`prompts/system.md`, `storage/.gitkeep`, `tests/`, and
`workflows/default.yaml`.

## Manifest

`app.yaml` keeps `entrypoint: main:run` and grants only the surfaces the app
uses: `llm.external.call`, context, memory, storage, calculator tool execution,
and `report.say`. Required capabilities include `agenticos.runtime.llm_chat`
and `llm.chat`.

## Entry Point

`main.py` exposes:

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs):
    ...
```

The app first calls:

- `ctx.llm.chat_json(...)` to request a constrained JSON greeting/report plan
  from Runtime-owned `RuntimeServer.llm_chat`.

The JSON plan must include `schema_version`, `planner_mode: llm`, `greeting`,
`report_message`, `memory_key`, `storage_path`, `tool_args`, and
`user_summary`. The app validates the plan deterministically, then calls:

- `ctx.kernel.context.put/get` to write and read task state.
- `ctx.kernel.memory.remember` to persist a memory note.
- `ctx.kernel.storage.mount/write` to create an artifact.
- `ctx.kernel.tool.call("calculator.add", ...)` to exercise a real kernel tool.
- `ctx.kernel.skill.call("report.say", ...)` to exercise a runtime skill.

The result contains `schema_version`, `success`, `app_id`, `message`, `steps`,
`planner_mode`, `plan`, `error_code`, `reason`, `syscall_ids`, and
`audit_ids`.

The app must not construct provider clients, read model keys, call provider
SDKs directly, or continue successfully if the Runtime LLM facade is
unavailable. LLM failures return stable codes such as `LLMCHAT_UNAVAILABLE` or
`LLM_PROVIDER_UNCONFIGURED`.

## Smoke

Bare kernel smoke:

```bash
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/hello_world_agent/tests
```

In this path one test asserts that a bare `KernelService` returns
`LLMCHAT_UNAVAILABLE` before any kernel execution. Another test injects a
Runtime-owned recording LLM facade; that path reaches context, memory, storage,
and tool steps, then `report.say` returns `SKILL_BACKEND_UNAVAILABLE` because a
bare `KernelService` has no runtime skill backend.

Real runtime smoke:

```bash
PYTHONPATH=. pytest -q agentic_runtime_src/tests/test_hello_world_agent_real_runtime.py
```

This starts `RuntimeServer`, injects a Runtime-owned test LLM facade, loads the
real skill registry, and writes report output through the file report sink.

## Change Parameters

Pass a custom message:

```bash
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/hello_world_agent/tests \
  --maxfail=1
```

For code paths, call `run(ctx, message="hello from my task")` from a Runtime
session or a focused test. The message is always planned through the system LLM
facade before the deterministic kernel steps run.

## Add Tests

Add tests under `agentic_apps/hello_world_agent/tests`. Keep boundary checks in
place:

```bash
python scripts/check_agentic_app_uses_template.py agentic_apps/hello_world_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
```

Next tutorial: `agentic_runtime_src/docs/tutorials/color_block_grasper_agent.md`.
