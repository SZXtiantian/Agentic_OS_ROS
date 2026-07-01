# Memory API

`ctx.memory` stores and recalls small pieces of app data by key. Use it for results, preferences, summaries, and other compact structured values.

## APIs

| API | Description |
| --- | --- |
| [`ctx.memory.remember(key, value)`](remember.md) | Store a value under a key. |
| [`ctx.memory.recall(key, default=None)`](recall.md) | Read a value by key. |

Large files, images, and run artifacts should not be placed in memory.
