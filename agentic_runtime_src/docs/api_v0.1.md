# Agentic App SDK API v0.1

本文档面向 Agent App 开发者，按照接口参考手册的形式说明当前稳定 API。Agent App 运行在 Agentic Runtime 之上，只编排任务级能力，不直接访问 ROS2、Nav2、MoveIt、传感器 topic 或机器人驱动。

参考阅读：

- 完整应用开发手册：`docs/app_developer_interface.md`
- App manifest：`docs/app_manifest_v0.1.md`
- Skill manifest：`docs/skill_manifest_v0.1.md`
- 结构化错误码：`docs/errors.md`

## 基本用法

Agent App 入口必须是 async 函数，并通过 Runtime 注入的 `AgentContext` 调用 SDK：

```python
from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, place: str = "厨房") -> dict:
    try:
        resolved = await ctx.world.resolve_place(place)
        await ctx.robot.navigate_to(resolved.name, timeout_s=120)
        inspection = await ctx.robot.inspect_area(resolved.name, timeout_s=60)
        await ctx.memory.remember("last_inspection", inspection.to_dict())
        await ctx.report.say(f"{resolved.name} 检查完成。")
        return {"success": True, "inspection": inspection.to_dict()}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

Agent App 必须在 `app.yaml` 中声明入口、权限和所需 capability：

```yaml
entrypoint: main:run
permissions:
  - robot.state.read
  - robot.move
  - robot.stop
  - world.read
  - perception.inspect
  - memory.read
  - memory.write
  - human.ask
  - report.say
required_capabilities:
  - robot.get_state
  - robot.navigate_to
  - robot.inspect_area
  - robot.stop
  - world.resolve_place
  - memory.remember
  - memory.recall
  - human.ask
  - report.say
```

## 架构边界

Agent App 只能调用高层 Agentic SDK。以下行为禁止出现在应用代码中：

- `import rclpy`
- 发布 `/cmd_vel`
- 直接订阅 `/scan`、`/odom`、`/tf`
- 直接调用 Nav2 或 MoveIt action
- 导入 ROS2 message package、bridge source、vendor driver 或硬件 SDK
- shell out 到 `ros2` 绕过 Runtime
- 让 LLM 或 Agent 逻辑执行实时闭环控制

所有危险机器人动作都必须经过 Runtime 的权限检查、access/intervention、资源锁、安全守卫和 audit log。

## 返回与错误模型

底层 skill 返回 `SkillResult`：

```python
SkillResult(
    success: bool,
    data: dict,
    error_code: str = "",
    reason: str = "",
    recoverable: bool = True,
    suggested_recovery: list[str] = [],
    audit_id: str = "",
)
```

高层 SDK 在成功时返回 dataclass 或 `SkillResult`；失败时通常抛出 `AgenticRuntimeError` 或其子类。应用应捕获结构化异常，而不是假设失败会以 `success=False` 返回。

常见异常映射：

| 错误码 | Python 异常 |
| --- | --- |
| `PERMISSION_DENIED`、`ACCESS_DENIED`、`ACCESS_INTERVENTION_REQUIRED` | `PermissionDeniedError` |
| `FORBIDDEN_ZONE`、`ESTOP_PRESSED`、`ROBOT_NOT_LOCALIZED`、`SAFETY_REJECTED` | `SafetyRejectedError` |
| `SKILL_TIMEOUT`、`NAVIGATION_TIMEOUT` | `SkillTimeoutError` |
| `RESOURCE_LOCKED` | `ResourceLockedError` |
| `SCHEMA_INVALID` | `SchemaInvalidError` |
| 其他错误码 | `AgenticRuntimeError` |

推荐处理方式：

```python
from agentic_runtime.errors import AgenticRuntimeError, SafetyRejectedError, SkillTimeoutError


async def navigate_safely(ctx, place: str) -> dict:
    try:
        await ctx.robot.navigate_to(place, timeout_s=120)
        return {"success": True}
    except SafetyRejectedError as exc:
        await ctx.robot.stop(reason=f"safety_rejected:{exc.code}")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except SkillTimeoutError as exc:
        await ctx.robot.stop(reason="navigation_timeout")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

## Stable Foundation API

这些接口是普通 Agent App 的首选、稳定开发面。

### `ctx.robot.get_state`

#### Basic Robot State Read

读取机器人当前状态。

```python
async def get_state() -> RobotState
```

Parameters:

- 无。

Returns:

- `RobotState`

`RobotState` 字段：

```python
robot_id: str
mode: str
battery_state: str
battery_percent: float
is_localized: bool
is_moving: bool
estop_pressed: bool
current_place: str
pose: dict[str, float]
active_task_id: str
state: dict
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `robot.get_state` |
| Required permission | `robot.state.read` |
| Backend | ROS2 service `/agentic/robot/get_state` |
| Resource lock | 无 |
| Timeout | `10s` |
| Audit | 记录结果 |

Common errors:

- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `UNEXPECTED_ERROR`

Example:

```python
state = await ctx.robot.get_state()
if state.estop_pressed:
    return {"success": False, "error_code": "ESTOP_PRESSED", "reason": "robot estop is pressed"}
```

### `ctx.robot.navigate_to`

#### Navigate To A Known Place

导航到已注册地点。应用传入地点名，不能传入速度、轨迹、Nav2 goal 或底层坐标控制。

```python
async def navigate_to(place: str, timeout_s: int = 120) -> SkillResult
```

Parameters:

- `place`: 已注册地点名，例如 `"厨房"`。
- `timeout_s`: 导航超时时间，范围 `1..300`，默认 `120`。

Returns:

- `SkillResult`。成功时 `result.data` 可包含 bridge 返回的 `result`。

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `robot.navigate_to` |
| Required permission | `robot.move` |
| Backend | ROS2 action `/agentic/robot/navigate_to_place` |
| Bridge backend | Nav2 `/navigate_to_pose` |
| Resource lock | `base` |
| Safety | known place、本地化、急停释放、禁区检查、最大线速度 `0.5m/s` |
| Timeout | `120s` |
| Audit | 记录 feedback 和 result |

Common errors:

- `PLACE_NOT_FOUND`
- `FORBIDDEN_ZONE`
- `ROBOT_NOT_LOCALIZED`
- `ESTOP_PRESSED`
- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_ACTION_UNAVAILABLE`
- `ROS_ACTION_TIMEOUT`
- `NAVIGATION_TIMEOUT`
- `NAVIGATION_FAILED`
- `SKILL_CANCELLED`

Example:

```python
place = await ctx.world.resolve_place("厨房")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is not allowed"}

await ctx.robot.navigate_to(place.name, timeout_s=120)
```

### `ctx.robot.inspect_area`

#### Inspect A Known Area

检查已注册地点并返回摘要、对象、异常和 evidence 信息。

```python
async def inspect_area(place: str, timeout_s: int = 60) -> InspectionResult
```

Parameters:

- `place`: 已注册地点名。
- `timeout_s`: 检查超时时间，范围 `1..120`，默认 `60`。

Returns:

- `InspectionResult`

`InspectionResult` 字段：

```python
success: bool
summary: str
objects: list[str]
anomalies: list[str]
evidence_path: str
evidence: dict
error_code: str
reason: str
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `robot.inspect_area` |
| Required permission | `perception.inspect` |
| Backend | ROS2 service `/agentic/perception/inspect_area` |
| Resource lock | `camera` |
| Safety | known place、允许取消、runtime timeout margin `5s` |
| Timeout | `60s` |
| Audit | 记录结果 |

Common errors:

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `RESOURCE_LOCKED`
- `SAFETY_REJECTED`
- `INSPECTION_FAILED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `SKILL_TIMEOUT`

Example:

```python
inspection = await ctx.robot.inspect_area("厨房", timeout_s=60)
await ctx.memory.remember(
    "last_inspection",
    {
        "place": "厨房",
        "summary": inspection.summary,
        "objects": inspection.objects,
        "anomalies": inspection.anomalies,
        "evidence_path": inspection.evidence_path,
    },
)
```

### `ctx.robot.stop`

#### Stop Or Cancel Robot Work

请求停止机器人或取消当前 session 的活跃任务。

```python
async def stop(reason: str = "app_requested") -> SkillResult
```

Parameters:

- `reason`: 停止原因，默认 `"app_requested"`。

Returns:

- `SkillResult`

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `robot.stop` |
| Required permission | `robot.stop` |
| Backend | ROS2 service `/agentic/robot/stop` |
| Resource lock | 无，不被 `base` 锁阻塞 |
| Safety | high priority、bypass normal queue、audit required |
| Timeout | `10s` |
| Audit | 记录结果 |

Common errors:

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`
- `UNEXPECTED_ERROR`

Example:

```python
try:
    await ctx.robot.navigate_to("厨房", timeout_s=120)
except Exception:
    await ctx.robot.stop(reason="navigation_exception")
    raise
```

### `ctx.world.resolve_place`

#### Resolve A Place Name

把用户输入或业务地点名解析为 Runtime 已注册地点。

```python
async def resolve_place(name: str) -> PlaceRef
```

Parameters:

- `name`: 地点名，例如 `"厨房"`、`"客厅"`。

Returns:

- `PlaceRef`

`PlaceRef` 字段：

```python
id: str
name: str
frame_id: str
pose: dict[str, float]
allowed: bool
metadata: dict
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `world.resolve_place` |
| Required permission | `world.read` |
| Backend | ROS2 service `/agentic/world/resolve_place` |
| Resource lock | 无 |
| Safety | 不要求急停释放，不要求 known place |
| Timeout | `10s` |
| Audit | 记录结果 |

Common errors:

- `PLACE_NOT_FOUND`
- `PERMISSION_DENIED`
- `ROS_BRIDGE_UNAVAILABLE`
- `ROS_SERVICE_UNAVAILABLE`

Example:

```python
place = await ctx.world.resolve_place("厨房")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is forbidden"}
```

### `ctx.memory.remember`

#### Remember App Data

写入应用级记忆。适合保存任务摘要、上次检查结果、用户偏好等；不要写入密钥、原始大图、视频或不可审计的隐私数据。

```python
async def remember(key: str, value: Any) -> SkillResult
```

Parameters:

- `key`: 记忆键。
- `value`: JSON-like 值。

Returns:

- `SkillResult`

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `memory.remember` |
| Required permission | `memory.write` |
| Backend | Runtime internal memory store，默认 SQLite |
| Resource lock | 无 |
| Timeout | `3s` |
| Audit | 记录结果 |

Common errors:

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`
- `SCHEMA_INVALID`

Example:

```python
await ctx.memory.remember("last_requested_place", "厨房")
```

### `ctx.memory.recall`

#### Recall App Data

读取应用级记忆。缺失或值为 `None` 时返回 `default`。

```python
async def recall(key: str, default: Any = None) -> Any
```

Parameters:

- `key`: 记忆键。
- `default`: 默认值。

Returns:

- 存储值；当 Runtime 返回 value 为 `None` 时返回 `default`。

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `memory.recall` |
| Required permission | `memory.read` |
| Backend | Runtime internal memory store，默认 SQLite |
| Resource lock | 无 |
| Timeout | `3s` |
| Audit | 记录结果 |

Common errors:

- `PERMISSION_DENIED`
- `MEMORY_PROVIDER_UNAVAILABLE`
- `MEMORY_BACKEND_UNAVAILABLE`
- `MEMORY_RESULT_INVALID`

Example:

```python
last = await ctx.memory.recall("last_inspection", default={})
```

### `ctx.human.ask`

#### Ask A Human Operator

向人询问问题或请求确认。当前实现使用 Runtime human file queue，不自动回答；没有 operator response 时返回超时。

```python
async def ask(
    question: str,
    options: list[str] | None = None,
    timeout_s: int = 60,
    require_confirmation: bool = False,
) -> HumanAnswer
```

Parameters:

- `question`: 问题文本。
- `options`: 可选答案列表。
- `timeout_s`: 等待 operator response 的时间，默认 `60`。
- `require_confirmation`: 是否把该请求视为确认流程。

Returns:

- `HumanAnswer`

`HumanAnswer` 字段：

```python
answered: bool
answer: str
reason: str
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `human.ask` |
| Required permission | `human.ask` |
| Backend | Runtime human file queue |
| Resource lock | 无 |
| Access | required，resource type 为 `human` |
| Timeout | `60s` |
| Audit | 记录结果 |

Common errors:

- `PERMISSION_DENIED`
- `ACCESS_INTERVENTION_REQUIRED`
- `HUMAN_BACKEND_UNAVAILABLE`
- `HUMAN_OPERATOR_TIMEOUT`
- `HUMAN_CANCELLED`

Example:

```python
answer = await ctx.human.ask(
    "导航失败，是否重试一次？",
    options=["重试", "取消任务"],
    timeout_s=30,
    require_confirmation=True,
)
if answer.answer != "重试":
    await ctx.robot.stop(reason="operator_cancelled_retry")
```

### `ctx.report.say`

#### Report A Message

向用户或运行日志报告消息。

```python
async def say(message: str) -> SkillResult
```

Parameters:

- `message`: 报告内容。

Returns:

- `SkillResult`

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `report.say` |
| Required permission | `report.say` |
| Backend | Runtime internal report sink |
| Resource lock | 无 |
| Timeout | `3s` |
| Audit | 记录结果 |

当前 report sink 会写入 `AGENTIC_REPORT_LOG` 或 `$AGENTIC_VAR/reports/report.jsonl`。安装后默认路径通常是 `/opt/agentic/var/reports/report.jsonl`。

Common errors:

- `PERMISSION_DENIED`
- `REPORT_BACKEND_UNAVAILABLE`
- `SKILL_BACKEND_UNAVAILABLE`

Example:

```python
await ctx.report.say("厨房检查完成，未发现异常。")
```

## Specialized Implemented API

以下接口已经实现，但依赖具体真实 provider、bridge 或应用场景。普通应用应先使用 Stable Foundation API。

### `ctx.llm.chat_json`

#### Runtime-Owned JSON Planning

调用 Runtime-owned LLM facade，返回受约束 JSON plan。Agent App 不创建 OpenAI、LiteLLM、vLLM 等 provider client，也不读取 API key。

```python
async def chat_json(
    *,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int | None = None,
) -> LLMJSONResult
```

Returns:

```python
success: bool
plan: dict
error_code: str
reason: str
metadata: dict
```

注意：该 API 失败时返回 `LLMJSONResult(success=False, ...)`，不通过 `raise_for_result()` 抛 skill 异常。

Common errors:

- `LLMCHAT_UNAVAILABLE`
- `LLM_PROVIDER_UNCONFIGURED`
- `LLM_PROVIDER_REQUEST_FAILED`
- `LLM_RESPONSE_INVALID`

Example:

```python
plan = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=f"User task: {task_text}",
)
if not plan.success:
    return {"success": False, "error_code": plan.error_code, "reason": plan.reason}
```

### `ctx.perception.observe`

#### Observe A Target

通过 AgenticOS camera bridge 观察 allowlist 中的目标。

```python
async def observe(target: str = "workspace", timeout_s: int = 10) -> ObservationResult
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `perception.observe` |
| Required permission | `perception.observe` |
| Backend | ROS2 service `/agentic/perception/observe` |
| Resource lock | `camera` |
| Safety | camera target allowlist、最大时长 `10s` |

Example:

```python
observation = await ctx.perception.observe(target="workspace", timeout_s=10)
```

### `ctx.perception.capture_photo`

#### Capture A Photo Evidence

拍照并返回 image、metadata 和 evidence 信息。

```python
async def capture_photo(
    target: str = "workspace",
    label: str = "photo",
    timeout_s: int = 5,
) -> PhotoCaptureResult
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `perception.capture_photo` |
| Required permission | `perception.capture` |
| Backend | ROS2 service `/agentic/perception/capture_photo` |
| Resource lock | `camera` |
| Safety | camera target allowlist、最大时长 `20s` |

Example:

```python
photo = await ctx.perception.capture_photo(target="workspace", label="before_pick")
await ctx.report.say(f"photo saved: {photo.image_path}")
```

### `ctx.arm.get_state`

#### Read Arm State

读取机械臂 readiness、active action、运动状态和夹爪 readiness。

```python
async def get_state() -> ArmState
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `arm.get_state` |
| Required permission | `arm.state.read` |
| Backend | ROS2 service `/agentic/arm/get_state` |
| Resource lock | 无 |
| Timeout | `5s` |

Example:

```python
arm_state = await ctx.arm.get_state()
if arm_state.is_moving:
    return {"success": False, "error_code": "RESOURCE_LOCKED", "reason": "arm is moving"}
```

### `ctx.arm.move_named`

#### Move Arm By Named Action

执行 allowlist 中的命名机械臂动作。`"home"` 和 `"init"` 会映射为 `"arm_home"`。

```python
async def move_named(name: str, timeout_s: int = 8) -> SkillResult
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `arm.move_named` |
| Required permission | `arm.move.named` |
| Backend | ROS2 action `/agentic/arm/move_named` |
| Resource lock | `arm` |
| Safety | named action allowlist、workspace bounds、急停释放 |
| Timeout | `8s` |

Example:

```python
await ctx.arm.move_named("home", timeout_s=8)
```

### `ctx.gripper.open`

#### Open Gripper

低力打开夹爪。

```python
async def open(timeout_s: int = 5) -> SkillResult
```

Equivalent:

```python
await ctx.gripper.set("open", force="low", timeout_s=timeout_s)
```

### `ctx.gripper.close`

#### Close Gripper

关闭夹爪。`force="low"` 会映射为 allowlist 命令 `"close_gripper_low_force"`。

```python
async def close(force: str = "low", timeout_s: int = 5) -> SkillResult
```

Equivalent:

```python
await ctx.gripper.set("close_gripper_low_force", force="low", timeout_s=timeout_s)
```

### `ctx.gripper.set`

#### Set Gripper Command

执行 allowlist 中的夹爪命令。

```python
async def set(
    command: str,
    force: str = "low",
    percentage: float | None = None,
    timeout_s: int = 5,
) -> SkillResult
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `gripper.set` |
| Required permission | `gripper.control` |
| Backend | ROS2 service `/agentic/gripper/set` |
| Resource lock | `gripper` |
| Safety | gripper allowlist、急停释放、最大时长 `5s` |
| Timeout | `5s` |

Example:

```python
await ctx.gripper.open()
await ctx.gripper.close(force="low")
```

### `ctx.storage.list_recent_photos`

#### List Recent Photo Evidence

读取 Runtime 管理的照片 evidence 索引。

```python
async def list_recent_photos(limit: int = 5) -> list[dict]
```

Runtime contract:

| 项 | 值 |
| --- | --- |
| Skill | `storage.list_recent_photos` |
| Required permission | `storage.read` |
| Backend | Runtime internal storage index |
| Limit range | `1..20` |
| Timeout | `5s` |

Example:

```python
photos = await ctx.storage.list_recent_photos(limit=3)
```

## Kernel SDK

`ctx.kernel` 是进阶接口，返回 `KernelSDKResult`：

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

可用命名空间：

| Namespace | Methods |
| --- | --- |
| `ctx.kernel.context` | `put`、`get`、`delete`、`list`、`snapshot`、`recover`、`compact`、`clear` |
| `ctx.kernel.memory` | `remember`、`add`、`search`、`get`、`update`、`delete`、`list`、`export`、`import_` |
| `ctx.kernel.storage` | `mount`、`mkdir`、`create_file`、`write`、`read`、`list`、`delete`、`stat`、`history`、`rollback`、`share`、`index`、`retrieve` |
| `ctx.kernel.tool` | `call`、`list`、`describe`、`load_manifest`、`unload`、`register_builtin`、`status`、`cancel` |
| `ctx.kernel.skill` | `call`、`list`、`describe`、`status`、`cancel` |
| `ctx.kernel.llm` | `chat`、`complete`、`embed`、`status`、`cancel` |
| `ctx.kernel.access` | `check`、`assert_allowed` |
| `ctx.kernel` | `status`、`cancel` |

Important constraints:

- 机器人动作优先使用 `ctx.robot.*`。
- `ctx.kernel.tool.call("robot.navigate_to", ...)` 会被拒绝，避免工具系统绕过机器人安全链。
- 高风险 storage、tool、skill、robot 或 human 操作可能触发 access/intervention。
- 不要依赖 Kernel manager、RuntimeServer、SkillExecutor、bridge client 的内部方法。

Example:

```python
result = await ctx.kernel.context.put("phase", "started")
if not result.success:
    return {"success": False, "error_code": result.error_code}
```

## 推荐工作流

### 房间巡检

```text
resolve_place -> get_state -> navigate_to -> inspect_area -> remember -> report.say
```

```python
async def run(ctx, place: str = "厨房") -> dict:
    resolved = await ctx.world.resolve_place(place)
    state = await ctx.robot.get_state()
    if state.estop_pressed:
        return {"success": False, "error_code": "ESTOP_PRESSED", "reason": "estop is pressed"}

    await ctx.robot.navigate_to(resolved.name, timeout_s=120)
    inspection = await ctx.robot.inspect_area(resolved.name, timeout_s=60)
    await ctx.memory.remember("last_inspection", inspection.to_dict())
    await ctx.report.say(f"{resolved.name} 检查完成。")
    return {"success": True, "inspection": inspection.to_dict()}
```

### 人工确认后导航

```text
resolve_place -> human.ask -> navigate_to
```

```python
place = await ctx.world.resolve_place("厨房")
answer = await ctx.human.ask(
    f"是否允许机器人导航到 {place.name}？",
    options=["允许", "取消"],
    timeout_s=30,
    require_confirmation=True,
)
if answer.answer != "允许":
    return {"success": False, "error_code": "HUMAN_CANCELLED", "reason": "operator declined"}
await ctx.robot.navigate_to(place.name)
```

### LLM 规划后执行

```text
llm.chat_json -> deterministic validation -> SDK calls -> audit/report
```

```python
plan = await ctx.llm.chat_json(system_prompt=system_prompt, user_prompt=task_text)
if not plan.success:
    return {"success": False, "error_code": plan.error_code, "reason": plan.reason}

target = plan.plan.get("place", "")
resolved = await ctx.world.resolve_place(target)
await ctx.robot.navigate_to(resolved.name)
```

LLM 只生成计划或意图；实际机器人动作仍必须经过 SDK/Runtime。

## Demo 与测试命令

开发 Agent App：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
```

Runtime 单元测试：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
PYTHONPATH=. pytest -q
```

真实 runtime smoke：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --json
```

没有真实 ROS2 bridge 时，机器人能力应返回 `ROS_BRIDGE_UNAVAILABLE`、`ROS_SERVICE_UNAVAILABLE`、`ROS_ACTION_UNAVAILABLE` 或其他结构化错误；不要把 bridge 缺失伪装成成功。

## API 速查表

| API | Skill | Permission | Return |
| --- | --- | --- | --- |
| `ctx.robot.get_state()` | `robot.get_state` | `robot.state.read` | `RobotState` |
| `ctx.robot.navigate_to(place, timeout_s=120)` | `robot.navigate_to` | `robot.move` | `SkillResult` |
| `ctx.robot.inspect_area(place, timeout_s=60)` | `robot.inspect_area` | `perception.inspect` | `InspectionResult` |
| `ctx.robot.stop(reason="app_requested")` | `robot.stop` | `robot.stop` | `SkillResult` |
| `ctx.world.resolve_place(name)` | `world.resolve_place` | `world.read` | `PlaceRef` |
| `ctx.memory.remember(key, value)` | `memory.remember` | `memory.write` | `SkillResult` |
| `ctx.memory.recall(key, default=None)` | `memory.recall` | `memory.read` | `Any` |
| `ctx.human.ask(question, options=None, timeout_s=60, require_confirmation=False)` | `human.ask` | `human.ask` | `HumanAnswer` |
| `ctx.report.say(message)` | `report.say` | `report.say` | `SkillResult` |
| `ctx.llm.chat_json(...)` | Runtime LLM facade | Runtime-owned | `LLMJSONResult` |
| `ctx.perception.observe(target="workspace", timeout_s=10)` | `perception.observe` | `perception.observe` | `ObservationResult` |
| `ctx.perception.capture_photo(target="workspace", label="photo", timeout_s=5)` | `perception.capture_photo` | `perception.capture` | `PhotoCaptureResult` |
| `ctx.arm.get_state()` | `arm.get_state` | `arm.state.read` | `ArmState` |
| `ctx.arm.move_named(name, timeout_s=8)` | `arm.move_named` | `arm.move.named` | `SkillResult` |
| `ctx.gripper.open(timeout_s=5)` | `gripper.set` | `gripper.control` | `SkillResult` |
| `ctx.gripper.close(force="low", timeout_s=5)` | `gripper.set` | `gripper.control` | `SkillResult` |
| `ctx.gripper.set(command, force="low", percentage=None, timeout_s=5)` | `gripper.set` | `gripper.control` | `SkillResult` |
| `ctx.storage.list_recent_photos(limit=5)` | `storage.list_recent_photos` | `storage.read` | `list[dict]` |
