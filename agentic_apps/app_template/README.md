# app_template

Agentic App development starts by copying `agentic_apps/app_template`.
开发 Agentic App 必须从 `agentic_apps/app_template` 复制开始。

This directory is the only standard template for native Agentic Apps in this
repository. Copy it directly or use `scripts/create_agentic_app.py`; do not
start by inventing a separate layout.

The template entrypoint has two real-only smoke paths.

The template is for the foundation-complete runtime surface. It does not claim
reserved providers as available; missing runtime backends return stable errors
such as `SKILL_BACKEND_UNAVAILABLE`, `ROS_BRIDGE_UNAVAILABLE`, or
`LLM_PROVIDER_UNCONFIGURED`.

## Natural Language Planning

The template does not force every app to call an LLM. If an app accepts natural
language and plans a task from that text, it must use the Agentic OS system LLM
facade:

```python
plan = await ctx.llm.chat_json(system_prompt=..., user_prompt=...)
```

`ctx.llm.chat_json` is a SDK wrapper over Runtime-owned
`RuntimeServer.llm_chat`. The app must not create provider clients, read model
keys, or call OpenAI/LiteLLM/vLLM SDKs directly. The LLM returns a constrained
JSON plan; the app then performs deterministic schema validation, policy
validation, safety checks, real capability calls, memory/storage writes, and
reporting. If the LLM facade or provider is unavailable, natural-language
planning returns a stable error and must not continue as a successful path.

## Bare Kernel Smoke

The bare kernel smoke uses a `KernelService` without a `RuntimeServer`. It calls:

- `ctx.kernel.context.put/get`
- `ctx.kernel.memory.remember`
- `ctx.kernel.storage.mount/write`
- `ctx.kernel.tool.call("calculator.add", ...)`
- `ctx.kernel.skill.call("report.say", ...)`

`report.say` requires a real Runtime skill backend. If the template is run with only a bare `KernelService`, the report step returns `SKILL_BACKEND_UNAVAILABLE` instead of pretending success.

```bash
PYTHONPATH=/home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src \
  pytest -q /home/ubuntu/Agentic_OS_ROS_publish/agentic_apps/app_template/tests/test_app_template_kernel_smoke.py
```

## Real Runtime Smoke

The real runtime smoke starts a real `RuntimeServer`, loads the real skill
registry, and uses the file report sink for `report.say`.

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
PYTHONPATH=. pytest -q tests/test_app_template_real_runtime.py
```

No runtime smoke uses a simulated runtime to make report or skill calls pass.
