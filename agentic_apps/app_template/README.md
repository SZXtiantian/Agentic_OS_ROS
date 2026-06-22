# app_template

Template layout for Agentic OS apps. Copy this directory and grant only the permissions required by the app.

The template entrypoint is a real kernel smoke path. It calls:

- `ctx.kernel.context.put/get`
- `ctx.kernel.memory.remember`
- `ctx.kernel.storage.mount/write`
- `ctx.kernel.tool.call("calculator.add", ...)`
- `ctx.kernel.skill.call("report.say", ...)`

`report.say` requires a real Runtime skill backend. If the template is run with only a bare `KernelService`, the report step returns `SKILL_BACKEND_UNAVAILABLE` instead of pretending success.
