# Memory API

`ctx.memory` 按 key 保存和读取 App 的小段数据。它适合结果、偏好、摘要和其他紧凑的结构化值。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.memory.remember(key, value)`](remember.md) | 把值保存到指定 key。 |
| [`ctx.memory.recall(key, default=None)`](recall.md) | 按 key 读取值。 |

大文件、图片和运行 artifact 不应该放在 memory 里。
