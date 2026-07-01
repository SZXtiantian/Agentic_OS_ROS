# ctx.perception.capture_photo

Capture a photo and return image, metadata, and evidence information.

## Signature

```python
async def capture_photo(
    target: str = "workspace",
    label: str = "photo",
    timeout_s: int = 5,
) -> PhotoCaptureResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `target` | `str` | `"workspace"` | Capture target |
| `label` | `str` | `"photo"` | Evidence label |
| `timeout_s` | `int` | `5` | Timeout |

## Returns

`PhotoCaptureResult`

```python
success: bool
image_path: str
metadata_path: str
evidence: dict
audit_id: str
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `perception.capture_photo` |
| Permission | `perception.capture` |
| Backend | ROS2 service `/agentic/perception/capture_photo` |
| Resource lock | `camera` |
| Timeout | `20s` |

## Example

```python
photo = await ctx.perception.capture_photo(target="workspace", label="before_pick")
```
