# Kernel API

`ctx.kernel` 是进阶 syscall facade，适合需要 context、memory、storage、tool、skill、access 等 Runtime/Kernel 能力的应用。普通机器人动作优先使用 `ctx.robot.*`。

所有 Kernel SDK 调用返回：

```python
KernelSDKResult(
    success: bool,
    response: Any = None,
    error_code: str = "",
    syscall_id: str = "",
    audit_id: str = "",
    metadata: dict = {},
    raw: Any = None,
)
```

## APIs

| Namespace | Methods |
| --- | --- |
| `ctx.kernel` | `status()`、`cancel(syscall_id="")` |
| `ctx.kernel.context` | `put`、`get`、`delete`、`list`、`snapshot`、`recover`、`compact`、`clear` |
| `ctx.kernel.memory` | `remember`、`add`、`search`、`get`、`update`、`delete`、`list`、`export`、`import_` |
| `ctx.kernel.storage` | `mount`、`mkdir`、`create_file`、`write`、`read`、`list`、`delete`、`stat`、`history`、`rollback`、`share`、`index`、`retrieve` |
| `ctx.kernel.tool` | `call`、`list`、`describe`、`load_manifest`、`unload`、`register_builtin`、`status`、`cancel` |
| `ctx.kernel.skill` | `call`、`list`、`describe`、`status`、`cancel` |
| `ctx.kernel.llm` | `chat`、`complete`、`embed`、`status`、`cancel` |
| `ctx.kernel.access` | `check`、`assert_allowed` |

## 重要约束

- `ctx.kernel.tool.call("robot.navigate_to", ...)` 会被拒绝，错误码是 `TOOL_FORBIDDEN_ROBOT_CAPABILITY`。
- 机器人动作仍应走 `ctx.robot.*` 或受控的 `ctx.kernel.skill.call(...)`。
- 高风险 storage、tool、skill、robot 或 human 操作可能触发 access/intervention。
- 不要依赖 Runtime/Kernel manager 内部类。

## Example

```python
result = await ctx.kernel.context.put("phase", "started")
if not result.success:
    return {"success": False, "error_code": result.error_code}
```
