# ctx.world.resolve_place

`resolve_place` resolves user text or a business place name into a registered Runtime place.

## Signature

```python
async def resolve_place(name: str) -> PlaceRef
```

## Parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `name` | `str` | Place name, such as `"kitchen"` |

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

| Item | Value |
| --- | --- |
| Skill | `world.resolve_place` |
| Permission | `world.read` |
| Backend | ROS2 service `/agentic/world/resolve_place` |
| Resource lock | None |
| Timeout | `10s` |

## Common Errors

- `PLACE_NOT_FOUND`
- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`

## Example

```python
place = await ctx.world.resolve_place("kitchen")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}
```
