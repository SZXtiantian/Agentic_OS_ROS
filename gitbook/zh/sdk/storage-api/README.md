# Storage API

`ctx.storage` 暴露 App 可见的 evidence 记录。当前 SDK 方法用于读取最近照片 evidence 记录。

直接操作 Runtime storage 文件时，使用 Agentic System Call facade：`ctx.kernel.storage.*`。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.storage.list_recent_photos(limit=5)`](list_recent_photos.md) | 列出最近照片 evidence 记录。 |
