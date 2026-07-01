# tool

Source: `agentic_runtime_src/agentic_os/kernel/tool`

`tool` 管理非机器人工具，包括内存注册工具、manifest 工具、冲突排除和默认关闭的 MCP shell。

## App 可用入口

```python
await ctx.kernel.tool.call(name, args)
await ctx.kernel.tool.list()
await ctx.kernel.tool.describe(name)
await ctx.kernel.tool.load_manifest(path)
await ctx.kernel.tool.unload(name)
await ctx.kernel.tool.status(call_id="")
await ctx.kernel.tool.cancel(call_id="")
```

## 安全边界

工具系统不能承载机器人能力。类似下面的调用必须被拒绝：

```python
await ctx.kernel.tool.call("robot.navigate_to", {"place": "kitchen"})
```

预期错误码：

```text
TOOL_FORBIDDEN_ROBOT_CAPABILITY
```

## 开发者注意

机器人、机械臂、夹爪、感知、ROS2、Nav2、MoveIt 和直接速度控制都不能做成 generic tool。
