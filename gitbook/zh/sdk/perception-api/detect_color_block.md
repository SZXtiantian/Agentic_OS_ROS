# perception.detect_color_block

检测指定颜色块。该能力是 system skill，通常由专用应用通过 `ctx.kernel.skill.call(...)` 调用。

## Signature

```python
await ctx.kernel.skill.call(
    "perception.detect_color_block",
    {"color": "red", "target": "workspace", "timeout_s": 30},
)
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `perception.detect_color_block` |
| 权限 | `perception.detect.color_block` |
| 资源锁 | `camera`, `color_block_detector` |
| Timeout | `30s` |

## Common Errors

- `COLOR_BLOCK_CAPABILITY_UNAVAILABLE`
- `COLOR_BLOCK_NOT_FOUND`
- `COLOR_BLOCK_COLOR_NOT_ALLOWED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`

## Example

```python
result = await ctx.kernel.skill.call(
    "perception.detect_color_block",
    {"color": "red", "target": "workspace", "timeout_s": 30},
)
```
