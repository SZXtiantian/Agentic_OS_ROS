# app_template

Template layout for Agentic OS apps. Copy this directory and grant only the permissions required by the app.

The template entrypoint has two real-only smoke paths.

The template is for the foundation-complete runtime surface. It does not claim
reserved providers as available; missing runtime backends return stable errors
such as `SKILL_BACKEND_UNAVAILABLE`, `ROS_BRIDGE_UNAVAILABLE`, or
`LLM_PROVIDER_UNCONFIGURED`.

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
