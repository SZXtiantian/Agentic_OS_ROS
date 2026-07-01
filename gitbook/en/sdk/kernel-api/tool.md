# ctx.kernel.tool

`ctx.kernel.tool` sends tool system calls for non-robot tool execution and tool registry management. Robot capabilities cannot use the tool system to bypass safety.

All methods return `KernelSDKResult`.

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

| Parameter | Description |
| --- | --- |
| `name` | Tool name. |
| `args` | Tool arguments. |
| `path` | Tool manifest path. |
| `call_id` | Call ID to inspect or cancel. |
| `metadata` / `kwargs` | Optional metadata, permissions, and `timeout_s`. |

## Safety

`ctx.kernel.tool.call("robot.navigate_to", ...)` is rejected with `TOOL_FORBIDDEN_ROBOT_CAPABILITY`.

## Example

```python
tools = await ctx.kernel.tool.list(timeout_s=5)
```
