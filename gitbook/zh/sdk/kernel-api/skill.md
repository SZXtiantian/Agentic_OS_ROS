# ctx.kernel.skill

`ctx.kernel.skill` 发送 skill system calls，用于列出、描述、调用、查询或取消 Runtime skill。具体 skill contract 后续在 skills 文档中整理；本页只描述 `skill_*` system call facade。

所有方法返回 `KernelSDKResult`。

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

| 参数 | 说明 |
| --- | --- |
| `name` | Runtime skill 名称。 |
| `args` | Runtime skill 参数。 |
| `call_id` | 要查询或取消的调用 ID。 |
| `permissions`, `timeout_s`, `kwargs` | 可选权限覆盖、超时和额外 metadata。 |

## Example

```python
result = await ctx.kernel.skill.call(
    "perception.detect_color_block",
    {"color": "red", "target": "workspace"},
    timeout_s=30,
)
```
