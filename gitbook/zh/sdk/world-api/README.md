# World API

`ctx.world` 用于解析地点和读取世界模型。当前稳定能力是 `resolve_place`；`get_places` 和 `locate_user` 在 SDK 中存在占位，但不应作为应用逻辑依赖。

## APIs

| API | 状态 | Skill | 权限 | 返回 |
| --- | --- | --- | --- | --- |
| `ctx.world.resolve_place(name)` | stable | `world.resolve_place` | `world.read` | `PlaceRef` |
| `ctx.world.get_places()` | unsupported placeholder | 无 | 无 | `[]` |
| `ctx.world.locate_user()` | unsupported placeholder | 无 | 无 | `None` |

## ctx.world.resolve_place

```python
async def resolve_place(name: str) -> PlaceRef
```

把用户输入或业务地点名解析为 Runtime 已注册地点。

`PlaceRef` 字段：

```python
id: str
name: str
frame_id: str
pose: dict[str, float]
allowed: bool
metadata: dict
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| 后端 | ROS2 service `/agentic/world/resolve_place` |
| 资源锁 | 无 |
| Timeout | `10s` |

常见错误：

- `PLACE_NOT_FOUND`
- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`

示例：

```python
place = await ctx.world.resolve_place("厨房")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}
```
