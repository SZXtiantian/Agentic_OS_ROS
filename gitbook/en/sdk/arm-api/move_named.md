# ctx.arm.move_named

`move_named`: Run a configured named arm motion.

```python
async def move_named(name: str, timeout_s: int = 8) -> SkillResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | `str` | required | Named motion. `"home"` and `"init"` map to `"arm_home"`. |
| `timeout_s` | `int` | `8` | Timeout for waiting for the motion to complete. |

## Returns

`SkillResult`

## Example

```python
await ctx.arm.move_named("home", timeout_s=8)
```
