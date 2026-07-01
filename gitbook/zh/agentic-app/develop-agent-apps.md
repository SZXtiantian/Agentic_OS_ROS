# 如何开发 Agent App

## 目录结构

```text
agentic_apps/my_agent/
  README.md
  app.yaml
  main.py
  prompts/system.md
  workflows/default.yaml
  storage/.gitkeep
  tests/
```

## 入口函数

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

返回值必须是 `dict`，并包含布尔字段 `success`。

## 禁止导入

不要在 Agent App 中导入 ROS2 client、message package、Nav2、MoveIt、bridge source 或硬件 SDK。
