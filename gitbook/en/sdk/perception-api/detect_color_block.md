# perception.detect_color_block

Detect a requested color block. This is a system skill, usually orchestrated by specialized apps through `ctx.kernel.skill.call(...)`.

## Signature

```python
await ctx.kernel.skill.call(
    "perception.detect_color_block",
    {"color": "red", "target": "workspace", "timeout_s": 30},
)
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `perception.detect_color_block` |
| Permission | `perception.detect.color_block` |
| Resource locks | `camera`, `color_block_detector` |
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
