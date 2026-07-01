# How to Use Agent Apps

An Agent App is task orchestration code running above Agentic Runtime. It is not a ROS2 package, not a bridge node, and not a hardware driver.

Typical flow:

```text
resolve_place -> get_state -> navigate_to -> inspect_area -> remember -> report.say
```

Agent Apps call SDK only:

```python
await ctx.world.resolve_place("kitchen")
await ctx.robot.navigate_to("kitchen")
await ctx.robot.inspect_area("kitchen")
await ctx.report.say("Inspection completed")
```

Runtime and bridge layers handle ROS2, Nav2, MoveIt, sensors, and drivers.
