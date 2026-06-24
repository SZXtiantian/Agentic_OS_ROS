# hello_world_agent

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

`hello_world_agent` is the first template-derived tutorial app. It keeps the
canonical template files and exercises real kernel surfaces:

- `ctx.kernel.context.put/get`
- `ctx.kernel.memory.remember`
- `ctx.kernel.storage.mount/write`
- `ctx.kernel.tool.call("calculator.add", ...)`
- `ctx.kernel.skill.call("report.say", ...)`

## Bare Kernel Smoke

The bare kernel smoke uses a `KernelService` without a `RuntimeServer`.
`report.say` needs a runtime skill backend, so this path returns
`SKILL_BACKEND_UNAVAILABLE` for the report step and still exposes syscall
metadata for the earlier kernel calls.

```bash
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/hello_world_agent/tests
```

## Real Runtime Smoke

The real runtime smoke starts `RuntimeServer`, loads the runtime skill registry,
and uses the file report sink for `report.say`.

```bash
PYTHONPATH=. pytest -q agentic_runtime_src/tests/test_hello_world_agent_real_runtime.py
```

Create a new app the same way:

```bash
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
```
