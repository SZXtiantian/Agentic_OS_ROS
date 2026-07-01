# tool

Source: `agentic_runtime_src/agentic_os/kernel/tool`

`tool` manages non-robot tools, including in-memory tools, manifest tools, conflict exclusion, and a disabled-by-default MCP shell.

## App-Facing Entry

```python
await ctx.kernel.tool.call(name, args)
await ctx.kernel.tool.list()
await ctx.kernel.tool.describe(name)
await ctx.kernel.tool.load_manifest(path)
await ctx.kernel.tool.unload(name)
await ctx.kernel.tool.status(call_id="")
await ctx.kernel.tool.cancel(call_id="")
```

## Safety Boundary

The tool system must not host robot capabilities. Calls like this must be rejected:

```python
await ctx.kernel.tool.call("robot.navigate_to", {"place": "kitchen"})
```

Expected error code:

```text
TOOL_FORBIDDEN_ROBOT_CAPABILITY
```

## Notes

Robot, arm, gripper, perception, ROS2, Nav2, MoveIt, and direct velocity control must not be generic tools.
