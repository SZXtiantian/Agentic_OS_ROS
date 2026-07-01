# Perception API

`ctx.perception` observes the environment and captures photo evidence for Agent Apps.

## APIs

| API | Description |
| --- | --- |
| [`ctx.perception.observe(target="workspace", timeout_s=10)`](observe.md) | Observe a target area and return a summary. |
| [`ctx.perception.capture_photo(target="workspace", label="photo", timeout_s=5)`](capture_photo.md) | Capture a photo and return evidence paths. |
