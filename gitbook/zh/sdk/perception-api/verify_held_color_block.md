# perception.verify_held_color_block

验证色块是否出现在夹爪持有 ROI 中。抓取类应用必须使用独立验证结果判断成功，不能只相信 pick backend。

## Signature

```python
await ctx.kernel.skill.call(
    "perception.verify_held_color_block",
    {"color": "red", "timeout_s": 30},
)
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `perception.verify_held_color_block` |
| 权限 | `perception.verify.color_block_held` |
| 资源锁 | `camera`, `color_block_detector` |
| Timeout | `30s` |

## Common Errors

- `COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE`
- `COLOR_BLOCK_PICK_VERIFICATION_FAILED`
- `COLOR_BLOCK_COLOR_NOT_ALLOWED`

## Example

```python
verification = await ctx.kernel.skill.call(
    "perception.verify_held_color_block",
    {"color": "red"},
)
```
