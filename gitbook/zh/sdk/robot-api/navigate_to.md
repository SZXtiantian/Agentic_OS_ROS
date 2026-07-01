# ctx.robot.navigate_to

`navigate_to`: 让机器人导航到一个地点名称。

```python
async def navigate_to(place: str, timeout_s: int = 120) -> SkillResult
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `place` | `str` | required | 地点名称。应来自 `ctx.world.resolve_place(...)` 或 App 已验证的地点名。 |
| `timeout_s` | `int` | `120` | 等待导航完成的超时时间。 |

## Returns

`SkillResult`

## Example

```python
place = await ctx.world.resolve_place("厨房")
result = await ctx.robot.navigate_to(place.name, timeout_s=120)
```
