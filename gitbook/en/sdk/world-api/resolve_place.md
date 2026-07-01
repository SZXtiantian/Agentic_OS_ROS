# ctx.world.resolve_place

`resolve_place`: Resolve a place name into a Runtime-usable `PlaceRef`.

```python
async def resolve_place(name: str) -> PlaceRef
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | `str` | required | Place name used by the app, such as `"kitchen"` or `"workspace"`. |

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
place = await ctx.world.resolve_place("kitchen")
await ctx.robot.navigate_to(place.name)
```
