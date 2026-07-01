# perception.verify_held_color_block

Verify whether the color block appears in the gripper-held ROI. Pick apps must use independent verification before returning success.

## Signature

```python
await ctx.kernel.skill.call(
    "perception.verify_held_color_block",
    {"color": "red", "timeout_s": 30},
)
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `perception.verify_held_color_block` |
| Permission | `perception.verify.color_block_held` |
| Resource locks | `camera`, `color_block_detector` |
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
