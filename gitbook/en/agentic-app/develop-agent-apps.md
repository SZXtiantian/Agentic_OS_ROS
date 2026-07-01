# How to Develop Agent Apps

## Directory structure

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

## Entrypoint

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

The return value must be a `dict` with a boolean `success` field.

## Forbidden imports

Do not import ROS2 clients, message packages, Nav2, MoveIt, bridge source, or hardware SDKs from an Agent App.
