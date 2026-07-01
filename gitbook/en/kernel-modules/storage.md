# storage

Source: `agentic_runtime_src/agentic_os/kernel/storage`

`storage` manages Runtime storage files, versions, indexes, retrieval, and artifact-safe operations.

## App-Facing Entry

High-level SDK:

```python
photos = await ctx.storage.list_recent_photos(limit=5)
```

Advanced API:

```python
await ctx.kernel.storage.mount("color_block_grasper_agent")
await ctx.kernel.storage.write("color_block_grasper_agent/result.json", result)
await ctx.kernel.storage.read("color_block_grasper_agent/result.json")
await ctx.kernel.storage.list("color_block_grasper_agent")
await ctx.kernel.storage.history("color_block_grasper_agent/result.json")
await ctx.kernel.storage.rollback("color_block_grasper_agent/result.json", version="...")
```

## Notes

- Paths must stay inside the Runtime storage root.
- Do not write system directories, audit directories, bridge workspaces, or ROS workspaces.
- Evidence photos, JSON results, and run records belong in storage.
