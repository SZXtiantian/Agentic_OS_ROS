# Kernel API

`ctx.kernel` is the advanced syscall facade for context, memory, storage, tool, skill, access, and Kernel operations. Ordinary robot actions should use `ctx.robot.*` first.

To understand these capabilities by Runtime source directory, see [Kernel Modules](../../kernel-modules/README.md).

All Kernel SDK calls return:

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
| `ctx.kernel.context` | `put`, `get`, `delete`, `list`, `snapshot`, `recover`, `compact`, `clear` |
| `ctx.kernel.memory` | `remember`, `add`, `search`, `get`, `update`, `delete`, `list`, `export`, `import_` |
| `ctx.kernel.storage` | `mount`, `mkdir`, `create_file`, `write`, `read`, `list`, `delete`, `stat`, `history`, `rollback`, `share`, `index`, `retrieve` |
| `ctx.kernel.tool` | `call`, `list`, `describe`, `load_manifest`, `unload`, `register_builtin`, `status`, `cancel` |
| `ctx.kernel.skill` | `call`, `list`, `describe`, `status`, `cancel` |
| `ctx.kernel.llm` | `chat`, `complete`, `embed`, `status`, `cancel` |
| `ctx.kernel.access` | `check`, `assert_allowed` |

## Constraints

- `ctx.kernel.tool.call("robot.navigate_to", ...)` is rejected with `TOOL_FORBIDDEN_ROBOT_CAPABILITY`.
- Robot actions should use `ctx.robot.*` or controlled `ctx.kernel.skill.call(...)`.
- High-risk storage, tool, skill, robot, or human operations may trigger access/intervention.
- Do not depend on Runtime/Kernel manager internals.

## Example

```python
result = await ctx.kernel.context.put("phase", "started")
if not result.success:
    return {"success": False, "error_code": result.error_code}
```
