# ctx.world.resolve_place

`resolve_place`: 把地点名称解析成 Runtime 可用的 `PlaceRef`。

```python
async def resolve_place(name: str) -> PlaceRef
```

## Parameters

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | required | App 中使用的地点名称，例如 `"厨房"` 或 `"workspace"`。 |

## Returns

`PlaceRef`

```python
PlaceRef(
    name: str,
    kind: str = "",
    frame_id: str = "map",
    pose: dict = {},
    metadata: dict = {},
)
```

## Example

```python
place = await ctx.world.resolve_place("厨房")
await ctx.robot.navigate_to(place.name)
```
