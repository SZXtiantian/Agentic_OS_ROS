# ctx.perception.capture_photo

`capture_photo`: 拍摄目标区域照片，并返回图片和 metadata 路径。

```python
async def capture_photo(
    target: str = "workspace",
    label: str = "photo",
    timeout_s: int = 5,
) -> PhotoCaptureResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `target` | `str` | `"workspace"` | 要拍摄的目标区域。 |
| `label` | `str` | `"photo"` | evidence 标签。 |
| `timeout_s` | `int` | `5` | 等待拍照完成的超时时间。 |

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
