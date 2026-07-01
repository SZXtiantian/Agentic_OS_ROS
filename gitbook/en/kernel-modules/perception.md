# perception

Source: `agentic_runtime_src/agentic_os/kernel/perception`

`perception` defines agent-friendly perception abstractions. Real sensors, cameras, and detection backends are connected through Runtime/bridge.

## App-Facing Entry

High-level SDK:

```python
await ctx.perception.observe(target="workspace")
await ctx.perception.capture_photo(target="workspace", label="before_pick")
```

System skills:

```python
await ctx.kernel.skill.call("perception.center_color_block", {...})
await ctx.kernel.skill.call("perception.detect_color_block", {...})
await ctx.kernel.skill.call("perception.verify_held_color_block", {...})
```

## Example App

`color_block_grasper_agent` uses:

```text
center_color_block -> detect_color_block -> capture_evidence -> post_pick_verify
```

Detection results must contain verifiable fields such as color, center, confidence, and camera position. Invalid detection data returns `COLOR_BLOCK_DETECTION_INVALID`.

## Notes

- Apps must not subscribe directly to camera topics, `/scan`, `/odom`, or `/tf`.
- Perception data must come through Runtime/bridge and system skills.
- Evidence photos should be stored in Runtime storage.
