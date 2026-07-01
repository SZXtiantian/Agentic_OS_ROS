# world_model

Source: `agentic_runtime_src/agentic_os/kernel/world_model`

`world_model` 管理机器人可理解的地点、区域和世界对象。

## App 可用入口

```python
place = await ctx.world.resolve_place("kitchen")
```

底层也可通过 system skill：

```python
await ctx.kernel.skill.call("world.resolve_place", {"name": "kitchen"})
```

## 当前状态

当前公开的 App 入口主要是地点解析。对象关系、动态地图、区域状态和世界模型更新 API 会在后续完善。

## 开发者注意

- 导航、巡检、放置目标都应该先解析成已注册地点。
- App 不应该绕过 world model 直接塞 Nav2 pose。
