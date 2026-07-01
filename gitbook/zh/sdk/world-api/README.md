# World API

`ctx.world` 解析 Agent App 使用的地点名称。App 通过这里传递地点名称，不在代码里硬编码 Nav2 pose。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.world.resolve_place(name)`](resolve_place.md) | 把地点名称解析成 `PlaceRef`。 |

`ctx.world.get_places()` 和 `ctx.world.locate_user()` 是预留方法，当前只返回占位结果。
