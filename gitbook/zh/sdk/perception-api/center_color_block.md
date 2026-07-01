# perception.center_color_block

抓取前对齐色块。该能力可能移动机械臂，因此需要 arm 资源锁和 named action 权限。

## Signature

```python
await ctx.kernel.skill.call(
    "perception.center_color_block",
    {"color": "red", "target": "workspace", "timeout_s": 8},
)
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `perception.center_color_block` |
| 权限 | `perception.center.color_block`, `arm.move.named` |
| 资源锁 | `camera`, `arm`, `color_block_detector` |
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
