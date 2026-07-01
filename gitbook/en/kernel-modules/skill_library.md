# skill_library

Source: `agentic_runtime_src/agentic_os/kernel/skill_library`

`skill_library` manages system skills, app skills, registry, and backend dispatch.

## App-Facing Entry

```python
await ctx.kernel.skill.call(name, args, timeout_s=10)
await ctx.kernel.skill.list()
await ctx.kernel.skill.describe(name)
await ctx.kernel.skill.status(call_id="")
await ctx.kernel.skill.cancel(call_id="")
```

## Skill Types

System skills live under:

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

App skills live under:

```text
agentic_apps/<app_name>/skills/<skill_name>/
  SKILL.md
  impl.py
```

`SKILL.md` is the contract. The backend implementation must exist or the `implementation` block must clearly point to a Runtime/bridge-owned entry.

## Notes

- Robot capabilities should be system skills.
- App-private business logic can be an app skill.
- App skills must not bypass system skills to execute real robot actions.
