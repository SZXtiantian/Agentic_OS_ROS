# Perception API

`ctx.perception` 用于观察环境和采集照片 evidence。

## APIs

| API | 说明 |
| --- | --- |
| [`ctx.perception.observe(target="workspace", timeout_s=10)`](observe.md) | 观察目标区域并返回摘要。 |
| [`ctx.perception.capture_photo(target="workspace", label="photo", timeout_s=5)`](capture_photo.md) | 拍照并返回 evidence 路径。 |
