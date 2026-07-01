# ctx.kernel.tool

Kernel tool API 管理非机器人工具调用。机器人 capability 不能通过 tool 系统绕过安全链。

## Methods

```python
await ctx.kernel.tool.call(name: str, args: dict | None = None, **metadata)
await ctx.kernel.tool.list(**kwargs)
await ctx.kernel.tool.describe(name: str, **kwargs)
await ctx.kernel.tool.load_manifest(path: str, **metadata)
await ctx.kernel.tool.unload(name: str, **metadata)
await ctx.kernel.tool.register_builtin(name: str, **metadata)
await ctx.kernel.tool.status(call_id: str = "", **kwargs)
await ctx.kernel.tool.cancel(call_id: str, **kwargs)
```

## Safety

`ctx.kernel.tool.call("robot.navigate_to", ...)` 会被拒绝，错误码是 `TOOL_FORBIDDEN_ROBOT_CAPABILITY`。

## Example

```python
tools = await ctx.kernel.tool.list()
```
