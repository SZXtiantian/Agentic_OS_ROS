# ctx.kernel.tool

Kernel tool API manages non-robot tool calls. Robot capabilities cannot use the tool system to bypass safety.

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

`ctx.kernel.tool.call("robot.navigate_to", ...)` is rejected with `TOOL_FORBIDDEN_ROBOT_CAPABILITY`.

## Example

```python
tools = await ctx.kernel.tool.list()
```
