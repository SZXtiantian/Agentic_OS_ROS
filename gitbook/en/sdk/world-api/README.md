# World API

`ctx.world` resolves places and reads world-model information. The stable API is `resolve_place`; `get_places` and `locate_user` exist as SDK placeholders and should not be used for app logic.

## APIs

| API | Status | Skill | Permission | Return |
| --- | --- | --- | --- | --- |
| `ctx.world.resolve_place(name)` | stable | `world.resolve_place` | `world.read` | `PlaceRef` |
| `ctx.world.get_places()` | unsupported placeholder | None | None | `[]` |
| `ctx.world.locate_user()` | unsupported placeholder | None | None | `None` |

## ctx.world.resolve_place

```python
async def resolve_place(name: str) -> PlaceRef
```

Resolve user text or a business place name into a registered Runtime place.

`PlaceRef` fields:

```python
id: str
name: str
frame_id: str
pose: dict[str, float]
allowed: bool
metadata: dict
```

Runtime contract:

| Item | Value |
| --- | --- |
| Backend | ROS2 service `/agentic/world/resolve_place` |
| Resource lock | None |
| Timeout | `10s` |

Common errors:

- `PLACE_NOT_FOUND`
- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`

Example:

```python
place = await ctx.world.resolve_place("kitchen")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}
```
