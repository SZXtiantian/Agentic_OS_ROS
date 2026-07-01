# ctx.world.resolve_place

`resolve_place` 将用户输入或业务地点名解析为 Runtime 已注册地点。

## Signature

```python
async def resolve_place(name: str) -> PlaceRef
```

## Parameters

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `str` | 地点名，例如 `"厨房"`、`"客厅"` |

## Returns

`PlaceRef`

```python
id: str
name: str
frame_id: str
pose: dict[str, float]
allowed: bool
metadata: dict
```

## Runtime Contract

| 项 | 值 |
| --- | --- |
| Skill | `world.resolve_place` |
| 权限 | `world.read` |
| 后端 | ROS2 service `/agentic/world/resolve_place` |
| 资源锁 | 无 |
| Timeout | `10s` |

## Common Errors

- `PLACE_NOT_FOUND`
- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`

## Example

```python
place = await ctx.world.resolve_place("厨房")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}
```
