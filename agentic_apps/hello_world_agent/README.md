# hello_world_agent

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

`hello_world_agent` is the first template-derived tutorial app. It keeps the
canonical template files and starts by planning from the user `message` or
`task_text` through `ctx.llm.chat_json`, the SDK facade over Runtime-owned
`RuntimeServer.llm_chat`.

The LLM must return a constrained JSON plan with `planner_mode: llm`,
`greeting`, `report_message`, `memory_key`, `storage_path`, `tool_args`, and
`user_summary`. The app validates that plan, then exercises real kernel
surfaces:

- `ctx.kernel.context.put/get`
- `ctx.kernel.memory.remember`
- `ctx.kernel.storage.mount/write`
- `ctx.kernel.tool.call("calculator.add", ...)`
- `ctx.kernel.skill.call("report.say", ...)`

The app does not create provider clients, read API keys, or call provider SDKs
directly. If the Runtime LLM facade is unavailable, it returns
`LLMCHAT_UNAVAILABLE` or an equivalent stable LLM error and does not continue as
a successful path.

## Bare Kernel Smoke

The bare kernel smoke uses a `KernelService` without a `RuntimeServer`.
The first test asserts `LLMCHAT_UNAVAILABLE`. A second test injects a
Runtime-owned recording LLM facade; that path reaches the kernel calls and then
returns `SKILL_BACKEND_UNAVAILABLE` at `report.say`, because a bare
`KernelService` has no runtime skill backend.

```bash
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/hello_world_agent/tests
```

## Real Runtime Smoke

The real runtime smoke starts `RuntimeServer`, loads the runtime skill registry,
injects a Runtime-owned test LLM facade, and uses the file report sink for
`report.say`.

```bash
PYTHONPATH=. pytest -q agentic_runtime_src/tests/test_hello_world_agent_real_runtime.py
```

Create a new app the same way:

```bash
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
```
