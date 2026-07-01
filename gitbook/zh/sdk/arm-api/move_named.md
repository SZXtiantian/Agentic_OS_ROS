# ctx.arm.move_named

`move_named`: 执行配置好的机械臂命名动作。

```python
async def move_named(name: str, timeout_s: int = 8) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | required | 命名动作。`"home"` 和 `"init"` 会映射为 `"arm_home"`。 |
| `timeout_s` | `int` | `8` | 等待动作完成的超时时间。 |

## Returns

`SkillResult`

## Example

```python
await ctx.arm.move_named("home", timeout_s=8)
```
