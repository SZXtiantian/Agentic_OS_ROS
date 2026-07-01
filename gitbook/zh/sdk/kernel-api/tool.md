# ctx.kernel.tool

`ctx.kernel.tool` 发送 tool system calls，用于非机器人工具调用和工具注册管理。机器人能力不能通过 tool 系统绕过安全链。

所有方法返回 `KernelSDKResult`。

## APIs

| API | System Call |
| --- | --- |
| `call(name, args=None, **metadata)` | `ToolQuery(operation_type="tool_call")` |
| `list(**kwargs)` | `ToolQuery(operation_type="tool_list")` |
| `describe(name, **kwargs)` | `ToolQuery(operation_type="tool_describe")` |
| `load_manifest(path, **metadata)` | `ToolQuery(operation_type="tool_load_manifest")` |
| `unload(name, **metadata)` | `ToolQuery(operation_type="tool_unload")` |
| `register_builtin(name, **metadata)` | `ToolQuery(operation_type="tool_register_builtin")` |
| `status(call_id="", **kwargs)` | `ToolQuery(operation_type="tool_status")` |
| `cancel(call_id, **kwargs)` | `ToolQuery(operation_type="tool_cancel")` |

## Signatures

```python
async def call(name: str, args: dict | None = None, **metadata) -> KernelSDKResult
async def list(**kwargs) -> KernelSDKResult
async def describe(name: str, **kwargs) -> KernelSDKResult
async def load_manifest(path: str, **metadata) -> KernelSDKResult
async def unload(name: str, **metadata) -> KernelSDKResult
async def register_builtin(name: str, **metadata) -> KernelSDKResult
async def status(call_id: str = "", **kwargs) -> KernelSDKResult
async def cancel(call_id: str, **kwargs) -> KernelSDKResult
```

## Parameters

| 参数 | 说明 |
| --- | --- |
| `name` | Tool 名称。 |
| `args` | Tool 参数。 |
| `path` | Tool manifest 路径。 |
| `call_id` | 要查询或取消的调用 ID。 |
| `metadata` / `kwargs` | 可选 metadata、permissions 和 `timeout_s`。 |

## Safety

`ctx.kernel.tool.call("robot.navigate_to", ...)` 会被拒绝，错误码是 `TOOL_FORBIDDEN_ROBOT_CAPABILITY`。

## Example

```python
tools = await ctx.kernel.tool.list(timeout_s=5)
```
