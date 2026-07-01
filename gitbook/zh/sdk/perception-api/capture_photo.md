# ctx.perception.capture_photo

拍照并返回 image、metadata 和 evidence 信息。

## Signature

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
| `target` | `str` | `"workspace"` | 拍摄目标 |
| `label` | `str` | `"photo"` | evidence 标签 |
| `timeout_s` | `int` | `5` | 超时时间 |

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

| 项 | 值 |
| --- | --- |
| Skill | `perception.capture_photo` |
| 权限 | `perception.capture` |
| 后端 | ROS2 service `/agentic/perception/capture_photo` |
| 资源锁 | `camera` |
| Timeout | `20s` |

## Example

```python
photo = await ctx.perception.capture_photo(target="workspace", label="before_pick")
```
