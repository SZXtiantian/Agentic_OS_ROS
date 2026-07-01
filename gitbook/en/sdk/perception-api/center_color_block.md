# perception.center_color_block

Center a color block before picking. This capability may move the arm, so it requires the arm lock and named-action permission.

## Signature

```python
await ctx.kernel.skill.call(
    "perception.center_color_block",
    {"color": "red", "target": "workspace", "timeout_s": 8},
)
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `perception.center_color_block` |
| Permission | `perception.center.color_block`, `arm.move.named` |
| Resource locks | `camera`, `arm`, `color_block_detector` |
| Timeout | `30s` |

## Safety

- camera target allowlist
- named action allowlist
- workspace bounds check
- estop released

## Example

```python
await ctx.kernel.skill.call(
    "perception.center_color_block",
    {"color": "red", "target": "workspace"},
)
```
