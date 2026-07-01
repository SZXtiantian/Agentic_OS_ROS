# ctx.kernel.skill

Kernel skill API can call Runtime skills directly. Ordinary robot actions should use `ctx.robot.*`; specialized skills can be orchestrated here.

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

Calls still pass through permission, access, safety, resource-lock, and audit checks.
