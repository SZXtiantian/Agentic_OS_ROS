# skill_library

Source: `agentic_runtime_src/agentic_os/kernel/skill_library`

`skill_library` 管理 system skills、app skills、registry 和 backend dispatch。

## App 可用入口

```python
await ctx.kernel.skill.call(name, args, timeout_s=10)
await ctx.kernel.skill.list()
await ctx.kernel.skill.describe(name)
await ctx.kernel.skill.status(call_id="")
await ctx.kernel.skill.cancel(call_id="")
```

## Skill 分类

System skill 位于：

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

App skill 位于：

```text
agentic_apps/<app_name>/skills/<skill_name>/
  SKILL.md
  impl.py
```

`SKILL.md` 是 contract，backend 实现必须存在或由 `implementation` 明确指向 Runtime/bridge 拥有的入口。

## 开发者注意

- 机器人能力应优先做成 system skill。
- App 私有业务逻辑可做成 app skill。
- App skill 不能绕过 system skill 去执行真实机器人动作。
