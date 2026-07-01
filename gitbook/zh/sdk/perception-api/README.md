# Perception API

`ctx.perception` 提供观察、拍照和 evidence 相关能力。色块检测/对齐/验证目前作为 system skill 暴露，通常由专用应用通过 `ctx.kernel.skill.call(...)` 编排。

## Direct SDK APIs

| API | Skill | 权限 | 资源锁 | 返回 |
| --- | --- | --- | --- | --- |
| `ctx.perception.observe(target="workspace", timeout_s=10)` | `perception.observe` | `perception.observe` | `camera` | `ObservationResult` |
| `ctx.perception.capture_photo(target="workspace", label="photo", timeout_s=5)` | `perception.capture_photo` | `perception.capture` | `camera` | `PhotoCaptureResult` |

## ctx.perception.observe

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

后端是 ROS2 service `/agentic/perception/observe`，受 camera target allowlist 和最大时长 `10s` 约束。

## ctx.perception.capture_photo

```python
async def capture_photo(
    target: str = "workspace",
    label: str = "photo",
    timeout_s: int = 5,
) -> PhotoCaptureResult
```

返回 `image_path`、`metadata_path`、`evidence` 和 `audit_id`。

## Color-block system skills

| Skill | 权限 | 资源锁 | 说明 |
| --- | --- | --- | --- |
| `perception.detect_color_block` | `perception.detect.color_block` | `camera`, `color_block_detector` | 检测指定颜色块 |
| `perception.center_color_block` | `perception.center.color_block`, `arm.move.named` | `camera`, `arm`, `color_block_detector` | 抓取前视觉对齐 |
| `perception.verify_held_color_block` | `perception.verify.color_block_held` | `camera`, `color_block_detector` | 验证色块在夹爪持有 ROI |

示例：

```python
photo = await ctx.perception.capture_photo(target="workspace", label="before_pick")
```
