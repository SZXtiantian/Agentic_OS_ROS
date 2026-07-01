# world_model

Source: `agentic_runtime_src/agentic_os/kernel/world_model`

`world_model` manages places, regions, and world objects the robot can understand.

## App-Facing Entry

```python
place = await ctx.world.resolve_place("kitchen")
```

It can also be called through a system skill:

```python
await ctx.kernel.skill.call("world.resolve_place", {"name": "kitchen"})
```

## Status

The current public App entry mainly resolves places. Object relations, dynamic maps, region state, and world model update APIs will be expanded later.

## Notes

- Navigation, inspection, and placement targets should resolve to registered places first.
- Apps should not bypass the world model by injecting raw Nav2 poses.
