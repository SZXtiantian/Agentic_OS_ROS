# ctx.perception.observe

Observe an allowlisted target such as the workspace.

## Signature

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

## Parameters

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `target` | `str` | `"workspace"` | Observation target |
| `timeout_s` | `int` | `10` | Timeout, range `1..10` |

## Returns

`ObservationResult`

```python
success: bool
summary: str
objects: list[str]
evidence_path: str
evidence: dict
```

## Runtime Contract

| Item | Value |
| --- | --- |
| Skill | `perception.observe` |
| Permission | `perception.observe` |
| Backend | ROS2 service `/agentic/perception/observe` |
| Resource lock | `camera` |
| Safety | camera target allowlist |

## Example

```python
observation = await ctx.perception.observe(target="workspace", timeout_s=10)
```
