# ctx.perception.capture_photo

`capture_photo`: Capture a photo of a target area and return image and metadata paths.

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
| `target` | `str` | `"workspace"` | Target area to capture. |
| `label` | `str` | `"photo"` | Evidence label. |
| `timeout_s` | `int` | `5` | Timeout for waiting for photo capture to complete. |

## Returns

`PhotoCaptureResult`

```python
PhotoCaptureResult(
    success: bool,
    image_path: str,
    metadata_path: str,
    evidence: dict,
    audit_id: str = "",
)
```

## Example

```python
photo = await ctx.perception.capture_photo(target="workspace", label="precheck")
await ctx.report.say(photo.image_path)
```
