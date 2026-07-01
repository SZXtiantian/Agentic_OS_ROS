# perception

Source: `agentic_runtime_src/agentic_os/kernel/perception`

`perception` 定义面向 Agent 的感知抽象。真实传感器、相机和检测 backend 由 Runtime/bridge 接入。

## App 可用入口

高层 SDK：

```python
await ctx.perception.observe(target="workspace")
await ctx.perception.capture_photo(target="workspace", label="before_pick")
```

System skills：

```python
await ctx.kernel.skill.call("perception.center_color_block", {...})
await ctx.kernel.skill.call("perception.detect_color_block", {...})
await ctx.kernel.skill.call("perception.verify_held_color_block", {...})
```

## 示例 App

`color_block_grasper_agent` 的顺序是：

```text
center_color_block -> detect_color_block -> capture_evidence -> post_pick_verify
```

检测结果必须包含可验证字段，例如颜色、中心点、confidence 和相机坐标。验证失败时返回 `COLOR_BLOCK_DETECTION_INVALID`。

## 开发者注意

- App 不能直接订阅相机 topic、`/scan`、`/odom` 或 `/tf`。
- 感知数据要通过 Runtime/bridge 和 system skill 返回。
- 证据图片应写入 Runtime storage。
