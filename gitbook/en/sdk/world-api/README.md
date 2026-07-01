# World API

`ctx.world` resolves place names used by Agent Apps. Apps pass place names through this API instead of hard-coding Nav2 poses.

## APIs

| API | Description |
| --- | --- |
| [`ctx.world.resolve_place(name)`](resolve_place.md) | Resolve a place name into a `PlaceRef`. |

`ctx.world.get_places()` and `ctx.world.locate_user()` are reserved and currently return placeholder values.
