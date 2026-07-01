# storage

Source: `agentic_runtime_src/agentic_os/kernel/storage`

`storage` 管理 Runtime storage 下的文件、版本、索引、检索和 artifact-safe 操作。

## App 可用入口

高层 SDK：

```python
photos = await ctx.storage.list_recent_photos(limit=5)
```

进阶 API：

```python
await ctx.kernel.storage.mount("color_block_grasper_agent")
await ctx.kernel.storage.write("color_block_grasper_agent/result.json", result)
await ctx.kernel.storage.read("color_block_grasper_agent/result.json")
await ctx.kernel.storage.list("color_block_grasper_agent")
await ctx.kernel.storage.history("color_block_grasper_agent/result.json")
await ctx.kernel.storage.rollback("color_block_grasper_agent/result.json", version="...")
```

## 开发者注意

- 路径必须留在 Runtime storage root 内。
- 不要写系统目录、audit 目录、bridge workspace 或 ROS workspace。
- 证据图片、JSON 结果和运行记录适合放 storage。
