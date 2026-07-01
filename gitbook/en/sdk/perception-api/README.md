# Perception API

`ctx.perception` provides observation, photo capture, and evidence-oriented capabilities. Color-block detection/alignment/verification are system skills usually orchestrated by specialized apps through `ctx.kernel.skill.call(...)`.

## Direct SDK APIs

| API | Skill | Permission | Resource lock | Return |
| --- | --- | --- | --- | --- |
| `ctx.perception.observe(target="workspace", timeout_s=10)` | `perception.observe` | `perception.observe` | `camera` | `ObservationResult` |
| `ctx.perception.capture_photo(target="workspace", label="photo", timeout_s=5)` | `perception.capture_photo` | `perception.capture` | `camera` | `PhotoCaptureResult` |

## ctx.perception.observe

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

The backend is ROS2 service `/agentic/perception/observe`, guarded by the camera target allowlist and max duration `10s`.

## ctx.perception.capture_photo

```python
async def capture_photo(
    target: str = "workspace",
    label: str = "photo",
    timeout_s: int = 5,
) -> PhotoCaptureResult
```

Returns `image_path`, `metadata_path`, `evidence`, and `audit_id`.

## Color-block system skills

| Skill | Permission | Resource locks | Purpose |
| --- | --- | --- | --- |
| `perception.detect_color_block` | `perception.detect.color_block` | `camera`, `color_block_detector` | Detect a requested color block |
| `perception.center_color_block` | `perception.center.color_block`, `arm.move.named` | `camera`, `arm`, `color_block_detector` | Visually align before pick |
| `perception.verify_held_color_block` | `perception.verify.color_block_held` | `camera`, `color_block_detector` | Verify the block in the gripper-held ROI |

Example:

```python
photo = await ctx.perception.capture_photo(target="workspace", label="before_pick")
```
