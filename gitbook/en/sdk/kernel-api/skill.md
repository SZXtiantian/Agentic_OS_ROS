# ctx.kernel.skill

`ctx.kernel.skill` sends skill system calls for listing, describing, calling, inspecting, or canceling Runtime skills. Specific skill contracts will be organized in the skills documentation; this page only describes the `skill_*` system call facade.

All methods return `KernelSDKResult`.

## APIs

| API | System Call |
| --- | --- |
| `call(name, args=None, **kwargs)` | `SkillQuery(operation_type="skill_call")` |
| `list(**kwargs)` | `SkillQuery(operation_type="skill_list")` |
| `describe(name, **kwargs)` | `SkillQuery(operation_type="skill_describe")` |
| `status(call_id="", **kwargs)` | `SkillQuery(operation_type="skill_status")` |
| `cancel(call_id="", **kwargs)` | `SkillQuery(operation_type="skill_cancel")` |

## Signatures

```python
async def call(name: str, args: dict | None = None, **kwargs) -> KernelSDKResult
async def list(**kwargs) -> KernelSDKResult
async def describe(name: str, **kwargs) -> KernelSDKResult
async def status(call_id: str = "", **kwargs) -> KernelSDKResult
async def cancel(call_id: str = "", **kwargs) -> KernelSDKResult
```

## Parameters

| Parameter | Description |
| --- | --- |
| `name` | Runtime skill name. |
| `args` | Runtime skill arguments. |
| `call_id` | Call ID to inspect or cancel. |
| `permissions`, `timeout_s`, `kwargs` | Optional permission override, timeout, and extra metadata. |

## Example

```python
result = await ctx.kernel.skill.call(
    "perception.detect_color_block",
    {"color": "red", "target": "workspace"},
    timeout_s=30,
)
```
