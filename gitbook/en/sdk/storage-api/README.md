# Storage API

`ctx.storage` exposes app-visible evidence records. The current SDK method reads recent photo evidence records.

For direct Runtime storage file operations, use the Agentic System Call facade `ctx.kernel.storage.*`.

## APIs

| API | Description |
| --- | --- |
| [`ctx.storage.list_recent_photos(limit=5)`](list_recent_photos.md) | List recent photo evidence records. |
