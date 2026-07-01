# 如何使用 Agent App

Agent App 是运行在 Agentic Runtime 之上的任务编排代码。它不是 ROS2 package，不是 bridge node，也不是硬件驱动。

Agent App 的典型流程：

```text
resolve_place -> get_state -> navigate_to -> inspect_area -> remember -> report.say
```

Agent App 只调用 SDK：

```python
await ctx.world.resolve_place("厨房")
await ctx.robot.navigate_to("厨房")
await ctx.robot.inspect_area("厨房")
await ctx.report.say("检查完成")
```

底层 ROS2、Nav2、MoveIt、传感器和驱动由 Runtime 与 bridge 层处理。
