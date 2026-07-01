# ctx.kernel.skill

Kernel skill API 可直接调用 Runtime skill。普通机器人动作优先使用 `ctx.robot.*`，专用 skill 才通过这里编排。

## Methods

```python
await ctx.kernel.skill.call(name: str, args: dict | None = None, **kwargs)
await ctx.kernel.skill.list(**kwargs)
await ctx.kernel.skill.describe(name: str, **kwargs)
await ctx.kernel.skill.status(call_id: str = "", **kwargs)
await ctx.kernel.skill.cancel(call_id: str = "", **kwargs)
```

## Example

```python
result = await ctx.kernel.skill.call(
    "perception.detect_color_block",
    {"color": "red", "target": "workspace"},
)
```

调用仍会经过 permission、access、safety、resource lock 和 audit。
