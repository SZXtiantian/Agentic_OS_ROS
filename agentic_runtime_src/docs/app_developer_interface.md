# Agentic OS App Developer Interface

本文档面向 Agent App 应用开发者，说明如何在当前仓库实现之上编写、运行、测试和调试 Agent App。它基于 README、AGENTS.md、`agentic_runtime_src/docs`、SDK/Runtime 源码、示例应用、测试、skill manifest、配置文件和 demo 脚本整理；未在当前实现中提供的能力会明确标注为 planned、reserved 或 unsupported。

## 1. 应用开发者视角

Agentic OS ROS 运行在 ROS2 之上，但 Agent App 不是 ROS2 package，也不是 Nav2、MoveIt 或机器人驱动的包装层。应用开发者只编排任务级能力，例如“解析地点、询问人、导航、检查、记忆、报告”，不直接接触底盘速度、传感器 topic、Nav2 action 或 MoveIt action。

当前分层是：

```text
User
  -> Agent App
  -> Agentic SDK
  -> Agentic Runtime / Kernel
  -> Permission Checks / Resource Locks / Safety Guards / Audit Logs
  -> Robot Capability Layer
  -> AgenticOS Hardware Adapter / ROS2 Bridge
  -> ROS2
  -> Robot Hardware
```

每层职责：

| 层 | 应用开发者需要知道什么 |
| --- | --- |
| Agent App | 你的业务编排代码，入口是 `async def run(ctx: AgentContext, **kwargs)`。 |
| Agentic SDK | 你调用的 Python SDK，例如 `ctx.robot.navigate_to(place)`。 |
| Runtime / Kernel | 加载 app manifest、检查权限、串行化机器人资源、执行 skill、记录 session/syscall/audit。 |
| Robot Capability Layer | 把 `robot.navigate_to`、`robot.inspect_area` 等高层能力映射到 bridge 后端。 |
| ROS2 Bridge | AgenticOS 拥有的 HAL/adapter。只有这里允许 `rclpy`，并把 Agentic 请求适配到 ROS2。 |
| ROS2 / Hardware | 继续负责实时控制、Nav2、MoveIt、传感器、驱动和真实机器人。 |

应用开发者不需要也不应该直接接触 ROS2，因为直接访问 ROS2 会绕过 Runtime 的权限检查、资源锁、安全守卫和审计日志。所有危险机器人动作必须先进入 Agentic Runtime，再由 AgenticOS-owned bridge 适配到底层系统。

## 2. Agent App 开发模型

### 2.1 目录结构

新应用从模板创建：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
```

模板包含：

```text
agentic_apps/my_agent/
  README.md
  app.yaml
  main.py
  prompts/system.md
  storage/.gitkeep
  tests/
  workflows/default.yaml
```

建议约定：

| 路径 | 用途 |
| --- | --- |
| `app.yaml` | 应用身份、入口、权限、需要的 capability、安全策略和运行限制。 |
| `main.py` | 应用入口。必须只调用 Agentic SDK/Kernel SDK，不导入 ROS2。 |
| `prompts/` | 应用拥有的 prompt；provider、model、secret 仍归 Runtime 管。 |
| `workflows/` | 记录任务流程形状，便于测试和审计。 |
| `storage/` | 应用自有输出目录。不要提交生成的照片、视频、audit、task log、密钥。 |
| `tests/` | manifest、边界、错误处理、权限失败和流程测试。 |

### 2.2 入口与生命周期

`app.yaml` 的 `entrypoint` 当前必须是 `module:function`，模板和检查脚本要求：

```yaml
entrypoint: main:run
```

`main.py` 入口：

```python
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs) -> dict:
    ...
```

Runtime 运行应用时会：

1. 读取 `app.yaml` 并构造 `AppManifest`。
2. 校验入口模块存在，并扫描应用源码中的禁用 ROS2/机器人底层访问模式。
3. 创建 session，并在 Kernel service 可用时创建/启动 agent lifecycle。
4. 创建 `AgentContext(executor, app_manifest, session_id, agent_id)`。
5. 调用 `await run(ctx, **kwargs)`。
6. 要求应用返回 `dict`，且必须包含布尔字段 `success`。
7. 写 session、context snapshot、syscall、audit 和必要 artifact。

应用返回值不符合结构时会被归一化为：

```python
{
    "success": False,
    "error_code": "APP_RESULT_INVALID",
    "reason": "...",
}
```

### 2.3 同步与异步调用

当前 SDK 面向应用入口提供 async API。Agent App 内部必须使用 `await`：

```python
state = await ctx.robot.get_state()
result = await ctx.robot.navigate_to("厨房", timeout_s=120)
```

不要在 `run()` 内部使用 `asyncio.run()`。CLI、测试或上层 Runtime 会负责事件循环。

### 2.4 `ctx` 上下文对象

`AgentContext` 当前挂载以下命名空间：

| 命名空间 | 当前定位 |
| --- | --- |
| `ctx.robot` | Foundation stable robot API：状态、导航、检查、停止。 |
| `ctx.world` | 地点解析。 |
| `ctx.memory` | 应用键值记忆。 |
| `ctx.human` | 人工询问/确认，使用真实 file queue provider。 |
| `ctx.report` | 报告输出，当前写 file report sink 并打印。 |
| `ctx.llm` | Runtime-owned LLM facade。应用不创建 provider client。 |
| `ctx.perception` | 专用真实感知能力，当前用于观察和拍照。 |
| `ctx.arm` / `ctx.gripper` | 专用真实机械臂/夹爪能力，受 allowlist、安全和 operator intervention 约束。 |
| `ctx.storage` | 当前提供照片 evidence 索引读取。 |
| `ctx.kernel` | 进阶 Kernel SDK：context/memory/storage/tool/skill/access 等 syscall facade。 |

对通用 Agent App，优先使用 Foundation stable API。专用感知、机械臂、夹爪、LLM 和 Kernel SDK 只在 app manifest 明确声明权限和 capability，并且测试覆盖失败路径后使用。

### 2.5 配置加载

`RuntimeConfig.load()` 当前按以下顺序寻找配置：

1. 显式传入的 config path。
2. `AGENTIC_RUNTIME_CONFIG`。
3. `AGENTIC_RUNTIME_SRC/configs/runtime.yaml`。
4. 仓库内 `agentic_runtime_src/configs/runtime.yaml`。
5. 当设置 `AGENTIC_HOME` 时，读取 `$AGENTIC_HOME/etc/agentic.yaml`。

常用环境变量：

| 变量 | 用途 |
| --- | --- |
| `AGENTIC_RUNTIME_SRC` | Runtime 源码根目录。 |
| `AGENTIC_APP_ROOT` | Agent App 根目录，默认类似 `agentic_apps`。 |
| `AGENTIC_SKILLS` | skill manifest 根目录，默认 `agentic_runtime_src/skills`。 |
| `AGENTIC_HOME` | 安装后的系统根，默认 `/opt/agentic`。 |
| `AGENTIC_VAR` | audit、memory、session、report 等运行时状态根目录。 |
| `AGENTIC_SESSION_ROOT` | session/syscall 存储目录。 |
| `AGENTIC_STORAGE_ROOT` | Runtime storage 根目录。 |
| `AGENTIC_CONTEXT_ROOT` | Runtime context 根目录。 |
| `AGENTIC_REPORT_LOG` | `report.say` 文件输出路径覆盖。 |
| `AGENTIC_OPERATOR_INTERVENTION_APPROVED` | CLI operator intervention 许可开关。 |
| `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION` | 允许真实机器人运动/机械臂动作的环境许可。 |
| `AGENTIC_REAL_ROBOT_ALLOW_MANIPULATION` | 允许真实抓取/放置类 manipulation 的环境许可。 |

配置中的 `mock`、`fake`、`stub`、`dummy`、`simulated` backend/type 值会被拒绝。生产 Runtime 没有离线成功后端。

## 3. Manifest、权限与资源声明

### 3.1 `app.yaml`

当前 `AppManifest` 读取这些字段：

```yaml
name: my_agent
version: 0.1.0
description: ...
entrypoint: main:run
permissions: []
required_capabilities: []
safety_policy: {}
runtime_limits: {}
```

语义：

| 字段 | 当前行为 |
| --- | --- |
| `permissions` | 应用拥有的 grant set。`SkillExecutor` 会用它匹配 skill manifest 的 `permission_requirements`。 |
| `required_capabilities` | 应用声明需要 Runtime/Kernel 提供的高层能力。用于可读性、测试和 capability truth。 |
| `safety_policy` | 应用级安全意图，例如是否允许自主导航、是否允许 manipulation、禁区、最大时长。当前真实 enforcement 主要由 Runtime safety guard 和 skill manifest 约束完成。 |
| `runtime_limits` | 并发、重试、记忆写入、LLM 规划等应用侧限制。 |

当前没有独立的 app manifest JSON Schema 文件作为运行时强校验；运行时通过 `AppManifest.from_dict()`、`AppValidator` 和测试检查关键字段。额外字段可被特定应用读取，但不属于通用 stable interface。

### 3.2 Skill manifest

每个公开 capability 都有 `agentic_runtime_src/skills/*.yaml`。关键字段：

```yaml
name: robot.navigate_to
permission_requirements:
  - robot.move
resource_requirements:
  locks:
    - base
safety_constraints:
  require_known_place: true
  require_localized: true
  require_estop_released: true
  forbidden_zone_check: true
timeout_s: 120
backend:
  type: ros2_action
observability:
  audit: true
```

调用顺序是：

1. JSON Schema 输入校验。
2. App manifest 权限检查。
3. Kernel access/intervention 检查。
4. Safety guard 检查。
5. 资源锁获取。
6. 超时/取消控制。
7. 后端 dispatch。
8. audit/syscall/session 记录。
9. 释放资源锁。

### 3.3 当前权限名

`configs/permissions.yaml` 当前列出的权限：

| 权限 | 用途 |
| --- | --- |
| `robot.state.read` | 读取机器人状态。 |
| `robot.move` | 通过高层能力导航机器人底盘。 |
| `robot.stop` | 停止或取消活跃机器人任务。 |
| `world.read` | 读取地点/世界模型。 |
| `perception.inspect` | 检查已知区域。 |
| `perception.observe` | 通过 AgenticOS camera bridge 观察 workspace。 |
| `perception.capture` | 通过 bridge 拍照并保存 evidence。 |
| `perception.center.color_block` | 抓取前低速视觉对齐色块。 |
| `perception.verify.color_block_held` | 验证色块在夹爪持有 ROI 中。 |
| `arm.state.read` | 读取机械臂 readiness 和 action 状态。 |
| `arm.move.named` | 执行 allowlist 中的命名机械臂动作。 |
| `gripper.control` | 执行 allowlist 中的低力夹爪命令。 |
| `memory.read` | 读取应用记忆。 |
| `memory.write` | 写应用记忆。 |
| `storage.read` | 读取 AgenticOS 管理的 evidence/artifact 索引。 |
| `human.ask` | 向人询问或确认。 |
| `report.say` | 向用户报告消息。 |

Current note: `manipulation.pick_color_block.yaml` 和 `manipulation_place_color_block.yaml` 当前要求 `manipulation.pick.color_block` 与 `manipulation.place.color_block`；这两个权限在 `configs/permissions.yaml` 的描述表中尚未补充，但示例应用会按 skill manifest 声明它们。应用开发者应以 skill manifest 的 `permission_requirements` 为执行准入准则。

## 4. SDK 能力总览

### 4.1 返回值与失败模型

底层 skill 统一返回 `SkillResult`：

```python
SkillResult(
    success: bool,
    data: dict,
    error_code: str,
    reason: str,
    recoverable: bool,
    suggested_recovery: list[str],
    audit_id: str,
)
```

高层 SDK 成功时通常返回 dataclass 或 `SkillResult`：

| API 类别 | 成功返回 |
| --- | --- |
| `ctx.robot.get_state()` | `RobotState` |
| `ctx.robot.navigate_to()` | `SkillResult` |
| `ctx.robot.inspect_area()` | `InspectionResult` |
| `ctx.robot.stop()` | `SkillResult` |
| `ctx.world.resolve_place()` | `PlaceRef` |
| `ctx.memory.remember()` | `SkillResult` |
| `ctx.memory.recall()` | 记忆值，缺失时返回 `default` |
| `ctx.human.ask()` | `HumanAnswer` |
| `ctx.report.say()` | `SkillResult` |

高层 SDK 失败时会调用 `raise_for_result()` 并抛 `AgenticRuntimeError` 或其子类：

| 错误 | Python 异常 |
| --- | --- |
| `PERMISSION_DENIED` | `PermissionDeniedError` |
| `FORBIDDEN_ZONE`、`ESTOP_PRESSED`、`ROBOT_NOT_LOCALIZED`、`SAFETY_REJECTED` | `SafetyRejectedError` |
| `SKILL_TIMEOUT`、`NAVIGATION_TIMEOUT` | `SkillTimeoutError` |
| `RESOURCE_LOCKED` | `ResourceLockedError` |
| `SCHEMA_INVALID` | `SchemaInvalidError` |
| 其他错误码 | `AgenticRuntimeError` |

因此推荐写法是 `try/except AgenticRuntimeError`，不要依赖失败时返回 `success=False`：

```python
from agentic_runtime.errors import AgenticRuntimeError, SafetyRejectedError, SkillTimeoutError


async def run(ctx, place: str = "厨房"):
    try:
        await ctx.robot.navigate_to(place, timeout_s=120)
    except SafetyRejectedError as exc:
        await ctx.robot.stop(reason=f"safety:{exc.code}")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except SkillTimeoutError as exc:
        await ctx.robot.stop(reason="navigation_timeout")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

### 4.2 安全语义

| 能力 | 安全语义 |
| --- | --- |
| 读状态/地点/记忆 | 不控制机器人，但仍需要权限和 audit。 |
| 导航 | 需要 `robot.move`、access/intervention、known place、本地化、急停释放、禁区检查、`base` 锁、audit。 |
| 检查/观察/拍照 | 需要 perception 权限、相机目标 allowlist、`camera` 锁、audit。 |
| 停止 | 高优先级，不受 `base` 锁阻塞，会取消当前 session 的 active calls，并调用 safety stop backend。 |
| 人工询问 | 使用真实 file queue，不自动回答；默认 intervention provider 会拒绝高风险 ask，测试或部署需显式配置 provider。 |
| 机械臂/夹爪/manipulation | 需要 allowlist、workspace bounds、急停释放、资源锁、operator intervention 和真实 bridge。 |
| LLM | 通过 `ctx.llm.chat_json` 或 Kernel LLM facade；Runtime 拥有 provider client、config 和 secret。 |

## 5. 当前已实现 API 参考

### 5.1 Stable Foundation API

#### `await ctx.robot.get_state()`

读取机器人状态。

| 项 | 值 |
| --- | --- |
| Skill | `robot.get_state` |
| 权限 | `robot.state.read` |
| 后端 | ROS2 service `/agentic/robot/get_state` |
| timeout | skill manifest 默认 `10s` |
| 返回 | `RobotState` |

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

常见错误：`PERMISSION_DENIED`、`ROS_BRIDGE_UNAVAILABLE`、`ROS_SERVICE_UNAVAILABLE`、`UNEXPECTED_ERROR`。

示例：

```python
state = await ctx.robot.get_state()
if state.estop_pressed:
    return {"success": False, "error_code": "ESTOP_PRESSED", "reason": "robot estop is pressed"}
```

#### `await ctx.robot.navigate_to(place, timeout_s=120)`

导航到已注册地点。

| 项 | 值 |
| --- | --- |
| Skill | `robot.navigate_to` |
| 参数 | `place: str`，`timeout_s: int = 120`，范围 `1..300` |
| 权限 | `robot.move` |
| 资源锁 | `base` |
| Safety | known place、本地化、急停释放、禁区检查、最大线速度 `0.5m/s` |
| 后端 | ROS2 action `/agentic/robot/navigate_to_place`，bridge 再接 Nav2 `/navigate_to_pose` |
| 返回 | `SkillResult`，成功时 `result.data` 可包含 bridge result |

常见错误：`PLACE_NOT_FOUND`、`FORBIDDEN_ZONE`、`ROBOT_NOT_LOCALIZED`、`ESTOP_PRESSED`、`PERMISSION_DENIED`、`ACCESS_INTERVENTION_REQUIRED`、`RESOURCE_LOCKED`、`SAFETY_REJECTED`、`ROS_BRIDGE_UNAVAILABLE`、`ROS_ACTION_UNAVAILABLE`、`ROS_ACTION_TIMEOUT`、`NAVIGATION_TIMEOUT`、`NAVIGATION_FAILED`、`SKILL_CANCELLED`。

重试建议：只对明确 transient 的导航失败进行有限重试。重试前用 `ctx.human.ask()` 或业务策略确认；遇到 `FORBIDDEN_ZONE`、`PERMISSION_DENIED`、`ACCESS_INTERVENTION_REQUIRED`、`ESTOP_PRESSED` 不应自动重试。

示例：

```python
await ctx.robot.navigate_to(place.name, timeout_s=120)
```

#### `await ctx.robot.inspect_area(place, timeout_s=60)`

检查已注册地点并返回摘要。

| 项 | 值 |
| --- | --- |
| Skill | `robot.inspect_area` |
| 参数 | `place: str`，`timeout_s: int = 60`，范围 `1..120` |
| 权限 | `perception.inspect` |
| 资源锁 | `camera` |
| Safety | known place，允许取消，runtime timeout margin `5s` |
| 后端 | ROS2 service `/agentic/perception/inspect_area` |
| 返回 | `InspectionResult` |

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

常见错误：`PERMISSION_DENIED`、`ACCESS_INTERVENTION_REQUIRED`、`RESOURCE_LOCKED`、`SAFETY_REJECTED`、`INSPECTION_FAILED`、`ROS_BRIDGE_UNAVAILABLE`、`ROS_SERVICE_UNAVAILABLE`、`SKILL_TIMEOUT`。

示例：

```python
inspection = await ctx.robot.inspect_area(place.name, timeout_s=60)
await ctx.memory.remember(
    "last_inspection",
    {"place": place.name, "summary": inspection.summary, "anomalies": inspection.anomalies},
)
```

#### `await ctx.robot.stop(reason="app_requested")`

请求停止机器人或取消当前任务。

| 项 | 值 |
| --- | --- |
| Skill | `robot.stop` |
| 参数 | `reason: str = "app_requested"` |
| 权限 | `robot.stop` |
| 资源锁 | 无；不会因 `base` 锁被阻塞 |
| Safety | high priority、bypass normal queue、audit required |
| 后端 | ROS2 service `/agentic/robot/stop` |
| 返回 | `SkillResult` |

常见错误：`PERMISSION_DENIED`、`ACCESS_INTERVENTION_REQUIRED`、`ROS_BRIDGE_UNAVAILABLE`、`ROS_SERVICE_UNAVAILABLE`、`UNEXPECTED_ERROR`。

示例：

```python
try:
    await ctx.robot.navigate_to(place, timeout_s=120)
except Exception:
    await ctx.robot.stop(reason="navigation_exception")
    raise
```

#### `await ctx.world.resolve_place(name)`

把自然语言地点名解析为已注册地点。

| 项 | 值 |
| --- | --- |
| Skill | `world.resolve_place` |
| 参数 | `name: str` |
| 权限 | `world.read` |
| 后端 | ROS2 service `/agentic/world/resolve_place` |
| 返回 | `PlaceRef` |

`PlaceRef` 字段：

```python
id: str
name: str
frame_id: str
pose: dict[str, float]
allowed: bool
metadata: dict
```

当前 `configs/places.yaml` 示例包含 `厨房`、`客厅` 和不允许的 `楼梯`。

常见错误：`PLACE_NOT_FOUND`、`PERMISSION_DENIED`、`ROS_BRIDGE_UNAVAILABLE`、`ROS_SERVICE_UNAVAILABLE`。

示例：

```python
place = await ctx.world.resolve_place("厨房")
if not place.allowed:
    return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place.name} is not allowed"}
```

#### `await ctx.memory.remember(key, value)`

写入应用记忆。

| 项 | 值 |
| --- | --- |
| Skill | `memory.remember` |
| 参数 | `key: str`，`value: Any` |
| 权限 | `memory.write` |
| 后端 | Runtime internal memory store，默认 SQLite |
| 返回 | `SkillResult` |

常见错误：`PERMISSION_DENIED`、`MEMORY_PROVIDER_UNAVAILABLE`、`MEMORY_RESULT_INVALID`、`SCHEMA_INVALID`。

示例：

```python
await ctx.memory.remember("last_requested_place", place.name)
```

#### `await ctx.memory.recall(key, default=None)`

读取应用记忆。

| 项 | 值 |
| --- | --- |
| Skill | `memory.recall` |
| 参数 | `key: str`，`default: Any = None` |
| 权限 | `memory.read` |
| 后端 | Runtime internal memory store，默认 SQLite |
| 返回 | 存储值；当返回 value 为 `None` 时返回 `default` |

常见错误：`PERMISSION_DENIED`、`MEMORY_PROVIDER_UNAVAILABLE`、`MEMORY_BACKEND_UNAVAILABLE`、`MEMORY_RESULT_INVALID`。

示例：

```python
last = await ctx.memory.recall("last_inspection", default={})
```

#### `await ctx.human.ask(question, options=None, timeout_s=60, require_confirmation=False)`

向人询问或请求确认。

| 项 | 值 |
| --- | --- |
| Skill | `human.ask` |
| 参数 | `question: str`，`options: list[str] | None`，`timeout_s: int = 60`，`require_confirmation: bool = False` |
| 权限 | `human.ask` |
| 后端 | Runtime human file queue |
| 返回 | `HumanAnswer(answered: bool, answer: str, reason: str)` |

当前 file queue 会写请求并等待外部 operator response；它不会自动填答案。没有 response 时返回 `HUMAN_OPERATOR_TIMEOUT`，取消时返回 `HUMAN_CANCELLED`。在完整 Runtime 路径中，`human.ask` 还会经过 access/intervention；默认 provider 可能返回 `ACCESS_INTERVENTION_REQUIRED`，需要部署方配置允许的人机介入流程。

常见错误：`PERMISSION_DENIED`、`ACCESS_INTERVENTION_REQUIRED`、`HUMAN_BACKEND_UNAVAILABLE`、`HUMAN_OPERATOR_TIMEOUT`、`HUMAN_CANCELLED`。

示例：

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

#### `await ctx.report.say(message)`

向用户报告消息。

| 项 | 值 |
| --- | --- |
| Skill | `report.say` |
| 参数 | `message: str` |
| 权限 | `report.say` |
| 后端 | Runtime internal report sink |
| 返回 | `SkillResult` |

当前 ROS2 CLI bridge client 中的 `report_say` 会打印 message，并写入 `AGENTIC_REPORT_LOG` 或 `$AGENTIC_VAR/reports/report.jsonl`，默认安装路径是 `/opt/agentic/var/reports/report.jsonl`。

常见错误：`PERMISSION_DENIED`、`REPORT_BACKEND_UNAVAILABLE`、`SKILL_BACKEND_UNAVAILABLE`。

示例：

```python
await ctx.report.say("厨房检查完成，未发现异常。")
```

### 5.2 Specialized implemented API

这些 API 当前在 SDK 和 skill manifests 中实现，并被示例应用使用。它们不是通用应用的默认起点；使用前必须声明对应权限和 capability，并准备真实 bridge/provider。

| API | Skill/capability | 权限 | 返回 | 备注 |
| --- | --- | --- | --- | --- |
| `await ctx.llm.chat_json(system_prompt=..., user_prompt=..., timeout_s=None)` | Runtime-owned LLM facade | 通常需要 `llm.external.call` | `LLMJSONResult` | Provider client、secret、重试归 Runtime；失败以 `success=False` 返回，不抛 skill 异常。 |
| `await ctx.perception.observe(target="workspace", timeout_s=10)` | `perception.observe` | `perception.observe` | `ObservationResult` | `camera` 锁，target allowlist。 |
| `await ctx.perception.capture_photo(target="workspace", label="photo", timeout_s=5)` | `perception.capture_photo` | `perception.capture` | `PhotoCaptureResult` | 返回 `image_path`、`metadata_path`、`evidence`。 |
| `await ctx.arm.get_state()` | `arm.get_state` | `arm.state.read` | `ArmState` | 读 readiness、active action、gripper readiness。 |
| `await ctx.arm.move_named(name, timeout_s=8)` | `arm.move_named` | `arm.move.named` | `SkillResult` | 只允许 `safety.yaml` 中的 named action；`home/init` 会映射为 `arm_home`。 |
| `await ctx.gripper.open(timeout_s=5)` | `gripper.set` | `gripper.control` | `SkillResult` | 低力 allowlist。 |
| `await ctx.gripper.close(force="low", timeout_s=5)` | `gripper.set` | `gripper.control` | `SkillResult` | `force="low"` 映射到 `close_gripper_low_force`。 |
| `await ctx.gripper.set(command, force="low", percentage=None, timeout_s=5)` | `gripper.set` | `gripper.control` | `SkillResult` | 受 gripper allowlist 和 pulse limits 约束。 |
| `await ctx.storage.list_recent_photos(limit=5)` | `storage.list_recent_photos` | `storage.read` | `list[dict]` | 读取 app 或 Runtime photo index。 |

Color-block 专用 skill 当前可通过 `ctx.kernel.skill.call(...)` 由专用应用编排：

| Skill | 权限 | 资源锁 | 当前状态 |
| --- | --- | --- | --- |
| `perception.detect_color_block` | `perception.detect.color_block` | `camera`, `color_block_detector` | real bridge required |
| `perception.center_color_block` | `perception.center.color_block`, `arm.move.named` | `camera`, `arm`, `color_block_detector` | real bridge required |
| `perception.verify_held_color_block` | `perception.verify.color_block_held` | `camera`, `color_block_detector` | real bridge required |
| `manipulation.pick_color_block` | `manipulation.pick.color_block` | `arm`, `gripper`, `camera`, `manipulation_backend` | real bridge required |
| `manipulation.place_color_block` | `manipulation.place.color_block` | `arm`, `gripper`, `manipulation_backend` | real bridge required |

### 5.3 Kernel SDK

`ctx.kernel` 当前暴露：

| 子命名空间 | 示例 |
| --- | --- |
| `ctx.kernel.context` | `put/get/delete/list/snapshot/recover/compact/clear` |
| `ctx.kernel.memory` | `remember/add/search/get/update/delete/list/export/import_` |
| `ctx.kernel.storage` | `mount/mkdir/create_file/write/read/list/delete/stat/history/rollback/share/index/retrieve` |
| `ctx.kernel.tool` | `call/list/describe/load_manifest/unload/register_builtin/status/cancel` |
| `ctx.kernel.skill` | `call/list/describe/status/cancel` |
| `ctx.kernel.llm` | `chat/complete/embed/status/cancel` |
| `ctx.kernel.access` | `check/assert_allowed` |
| `ctx.kernel.cancel` | 按 syscall id 请求取消 |

这些调用返回 `KernelSDKResult(success, response, error_code, syscall_id, audit_id, metadata, raw)`。它们适合需要 context/storage/tool/syscall 的进阶应用。注意：

- `ctx.kernel.tool.call("robot.navigate_to", ...)` 被拒绝，错误码是 `TOOL_FORBIDDEN_ROBOT_CAPABILITY`。
- 机器人动作仍应走 `ctx.robot.*` 或受控的 `ctx.kernel.skill.call(...)`，不能通过工具系统绕过安全链。
- `storage.delete`、`storage.rollback`、`storage.share`、tool install/uninstall/register 等高风险操作会触发 access intervention。
- 不要依赖 Runtime/Kernel manager 内部类、bridge client、ROS2 message 类型或 vendor SDK。

## 6. 安全与权限模型

所有危险机器人动作必须经过：

1. **Permission check**：App `permissions` 必须覆盖 skill manifest 的 `permission_requirements`。
2. **Kernel access/intervention**：机器人动作、human ask、tool/storage 高风险操作会进入 access policy。默认 intervention provider 是 deny-by-default。
3. **Safety guard**：需要时调用 `/agentic/safety/check`，检查急停、本地化、禁区、相机 target allowlist、命名动作 allowlist、workspace bounds、夹爪 allowlist 等。
4. **Resource lock**：例如导航锁 `base`，检查/拍照锁 `camera`，机械臂动作锁 `arm`，夹爪锁 `gripper`。
5. **Audit log**：成功、失败、权限拒绝、安全拒绝、资源锁失败、超时、取消和后端失败都写 audit。

移动、导航、检查和停止的边界：

| 动作 | 边界 |
| --- | --- |
| 导航 | 应用只能给地点名/地点引用，不能给 `/cmd_vel`、速度曲线或 Nav2 goal action。 |
| 检查 | 应用只能请求检查地点或目标，不直接订阅图像、激光、里程计或 TF。 |
| 停止 | 应用可以调用 `ctx.robot.stop()`；底层停止由 Agentic safety bridge 执行并审计。 |
| 机械臂 | 应用只能执行 allowlist 命名动作或专用 manipulation skill，不能下发关节、力矩、servo、MoveIt action。 |
| LLM | LLM 可参与规划和决策，但不得进入实时闭环控制。 |

## 7. 明确禁止事项

Agent App 禁止：

- `import rclpy` 或 `from rclpy ...`。
- 发布 `/cmd_vel`。
- 直接订阅 `/scan`、`/odom`、`/tf`。
- 直接调用 Nav2 action，例如 `NavigateToPose`。
- 直接调用 MoveIt action 或 `MoveGroup`。
- 创建 ROS2 publisher/subscription/action client。
- 导入 ROS2 message package、bridge source、robot vendor SDK 或 hardware driver。
- shell out 到 `ros2` 来绕过 Runtime。
- 把 LLM/Agent 逻辑放入实时闭环控制。
- 绕过 permission/resource lock/safety/audit 调用机器人底层能力。
- 在应用里创建 OpenAI/LiteLLM/vLLM provider client、读取模型 API key 或绕过 `ctx.llm.chat_json`。

仓库提供检查：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/check_agentic_app_boundaries.py agentic_apps
```

## 8. 错误处理与结构化错误码

### 8.1 常见错误码

| 场景 | 错误码 |
| --- | --- |
| 权限不足 | `PERMISSION_DENIED`、`ACCESS_DENIED` |
| 操作需要人工介入 | `ACCESS_INTERVENTION_REQUIRED`、`ACCESS_INTERVENTION_DENIED` |
| 资源被锁 | `RESOURCE_LOCKED` |
| 输入不符合 skill schema | `SCHEMA_INVALID` |
| 地点不存在/不可用 | `PLACE_NOT_FOUND`、`FORBIDDEN_ZONE` |
| 机器人状态不满足 | `ROBOT_NOT_LOCALIZED`、`ESTOP_PRESSED` |
| 安全守卫拒绝 | `SAFETY_REJECTED` |
| Runtime/skill 超时 | `SKILL_TIMEOUT`、`NAVIGATION_TIMEOUT` |
| 取消 | `SKILL_CANCELLED`、`SESSION_STOPPED` |
| ROS2 bridge 缺失 | `ROS_BRIDGE_UNAVAILABLE` |
| ROS2 service/action 缺失 | `ROS_SERVICE_UNAVAILABLE`、`ROS_ACTION_UNAVAILABLE` |
| ROS bridge mode 不支持 | `ROS_BRIDGE_MODE_UNSUPPORTED` |
| LLM 未配置/不可用 | `LLMCHAT_UNAVAILABLE`、`LLM_PROVIDER_UNCONFIGURED`、`LLM_PROVIDER_REQUEST_FAILED`、`LLM_RESPONSE_INVALID` |
| Human provider/queue | `HUMAN_PROVIDER_UNCONFIGURED`、`HUMAN_BACKEND_UNAVAILABLE`、`HUMAN_OPERATOR_TIMEOUT`、`HUMAN_CANCELLED` |
| Storage/tool/memory backend | `STORAGE_PATH_INVALID`、`TOOL_FORBIDDEN`、`TOOL_NOT_FOUND`、`MEMORY_PROVIDER_UNAVAILABLE` |
| 真实依赖未验证 | `UNVERIFIED_REAL_DEPENDENCY` |
| 专用色块/机械臂能力 | `COLOR_BLOCK_CAPABILITY_UNAVAILABLE`、`COLOR_BLOCK_PICK_VERIFICATION_UNAVAILABLE`、`COLOR_BLOCK_PICK_VERIFICATION_FAILED`、`MANIPULATION_BACKEND_UNAVAILABLE` |
| 未预期异常 | `UNEXPECTED_ERROR` |

### 8.2 应用侧处理策略

推荐把错误分成四类：

| 类别 | 示例 | 处理 |
| --- | --- | --- |
| 不可自动恢复 | `PERMISSION_DENIED`、`ACCESS_INTERVENTION_REQUIRED`、`FORBIDDEN_ZONE`、`ESTOP_PRESSED` | 停止危险动作，报告给用户，等待配置/操作员处理。 |
| 可有限重试 | `ROS_SERVICE_UNAVAILABLE`、`ROS_ACTION_UNAVAILABLE`、`NAVIGATION_TIMEOUT`、`SKILL_TIMEOUT` | 最多按 `runtime_limits.max_retries_per_skill` 重试；重试前可 `ctx.human.ask()`。 |
| 后端缺失 | `ROS_BRIDGE_UNAVAILABLE`、`LLM_PROVIDER_UNCONFIGURED`、`HUMAN_BACKEND_UNAVAILABLE` | 返回稳定失败，不编造成功。 |
| 业务降级 | `PLACE_NOT_FOUND`、`HUMAN_OPERATOR_TIMEOUT`、`INSPECTION_FAILED` | 报告原因，写 memory，必要时停止/取消。 |

示例：

```python
from agentic_runtime.errors import AgenticRuntimeError, ResourceLockedError, SafetyRejectedError, SkillTimeoutError


async def safe_navigation(ctx, place_name: str) -> dict:
    try:
        place = await ctx.world.resolve_place(place_name)
        if not place.allowed:
            return {"success": False, "error_code": "FORBIDDEN_ZONE", "reason": f"{place_name} is forbidden"}
        await ctx.robot.navigate_to(place.name, timeout_s=120)
        return {"success": True, "place": place.to_dict()}
    except ResourceLockedError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message, "next_action": "retry later"}
    except SafetyRejectedError as exc:
        await ctx.robot.stop(reason=f"safety_rejected:{exc.code}")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except SkillTimeoutError as exc:
        await ctx.robot.stop(reason="navigation_timeout")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except AgenticRuntimeError as exc:
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

## 9. 审计与可观测性

### 9.1 Audit log

`AuditLogger` 写 JSONL。默认路径来自 `runtime.audit_log_path`，仓库配置中是 `var/audit/audit.jsonl`，安装后通常在 `/opt/agentic/var/audit/audit.jsonl`。

每条记录包含：

```json
{
  "audit_id": "audit_000001",
  "timestamp": "...",
  "app_id": "room_inspection_app",
  "session_id": "sess_...",
  "skill_name": "robot.navigate_to",
  "args": {"place": "厨房", "timeout_s": 120},
  "permission_result": "allowed",
  "safety_result": "allowed",
  "resource_lock_result": "locked",
  "backend": "ros2_action",
  "status": "succeeded",
  "error_code": "",
  "duration_ms": 1234,
  "result": {"success": true}
}
```

### 9.2 Session 和 syscall

查看 session：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli sessions --limit 5
python -m agentic_runtime.cli session <session_id> --json
```

查看 audit：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli audit --limit 20 --json
```

查看 provider/capability 状态：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli status --json
python -m agentic_runtime.cli skills --json
python -m agentic_runtime.cli apps --json
```

### 9.3 Report 输出

`ctx.report.say()` 当前写 file report sink。查看方式：

```bash
tail -n 20 /opt/agentic/var/reports/report.jsonl
```

本地测试可设置：

```bash
export AGENTIC_REPORT_LOG=/tmp/agentic-report.jsonl
```

## 10. 本地开发、测试与 Demo 流程

### 10.1 安装依赖

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m pip install -e ".[dev]"
```

### 10.2 运行 Runtime 单元测试

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
PYTHONPATH=. pytest -q
```

### 10.3 运行工作区检查

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_agentic_app_tutorials.sh
python scripts/check_agentic_app_boundaries.py agentic_apps
```

### 10.4 创建和测试新应用

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py my_agent
python scripts/check_agentic_app_uses_template.py agentic_apps/my_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
```

### 10.5 没有真实机器人时如何验证

当前 Runtime 不提供成功路径的离线机器人后端。没有 ROS2/bridge/robot 时，机器人能力应返回稳定失败，例如 `ROS_BRIDGE_UNAVAILABLE` 或 `UNVERIFIED_REAL_DEPENDENCY`。应用开发者仍然可以验证：

- manifest 字段是否正确；
- 禁止 ROS2 访问的静态检查是否通过；
- SDK 调用顺序和错误处理是否正确；
- 权限不足时是否失败；
- bridge 缺失时是否返回结构化错误；
- memory/report/storage 等非机器人路径是否按预期工作；
- human queue 是否在无 response 时 timeout，而不是自动回答。

示例命令：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/room_inspection_app/tests
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
python -m agentic_runtime.cli run-app room_inspection_app --place 厨房 --json
```

第二条命令在没有真实 ROS2 bridge 时应失败，并显示 bridge 相关错误码；这仍然是正确的本地开发信号。

### 10.6 真实 bridge / robot demo

真实 room inspection demo：

```bash
/opt/agentic/bin/agentic-run inspection_agent --place 厨房 --real
```

源码侧脚本：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish/agentic_runtime_src
scripts/run_demo_app.sh 厨房
```

构建 ROS2 bridge package 的路径属于 bridge/HAL 开发，不是 Agent App 开发路径：

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/agentic_ws
colcon --log-base log/ros2_bridge build \
  --base-paths ros2_bridge_src \
  --build-base build/ros2_bridge \
  --install-base install/ros2_bridge \
  --packages-select \
  agentic_msgs \
  agentic_world_model \
  agentic_safety_guard \
  agentic_capability_bridge \
  agentic_app_runtime_bridge
```

## 11. 最小完整示例

以下示例展示 `resolve_place -> ask/permission -> navigate_to -> inspect_area -> remember -> report.say`。注意：这是应用代码形状；真实运行仍需要 manifest 权限、Runtime access/intervention、safety bridge 和 ROS2 bridge。

```python
from __future__ import annotations

from agentic_runtime.errors import AgenticRuntimeError, SafetyRejectedError, SkillTimeoutError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, place: str = "厨房") -> dict:
    await ctx.report.say(f"准备检查 {place}")

    try:
        resolved = await ctx.world.resolve_place(place)
        if not resolved.allowed:
            return {
                "success": False,
                "error_code": "FORBIDDEN_ZONE",
                "reason": f"{place} is not allowed",
            }

        answer = await ctx.human.ask(
            question=f"是否允许机器人导航到 {resolved.name} 并执行检查？",
            options=["允许", "取消"],
            timeout_s=30,
            require_confirmation=True,
        )
        if answer.answer != "允许":
            await ctx.robot.stop(reason="operator_declined")
            return {"success": False, "error_code": "HUMAN_CANCELLED", "reason": "operator declined"}

        state = await ctx.robot.get_state()
        if state.estop_pressed:
            return {"success": False, "error_code": "ESTOP_PRESSED", "reason": "estop is pressed"}

        await ctx.robot.navigate_to(resolved.name, timeout_s=120)
        inspection = await ctx.robot.inspect_area(resolved.name, timeout_s=60)

        memory_value = {
            "place": resolved.to_dict(),
            "summary": inspection.summary,
            "objects": inspection.objects,
            "anomalies": inspection.anomalies,
            "evidence_path": inspection.evidence_path,
        }
        await ctx.memory.remember("last_inspection", memory_value)

        if inspection.anomalies:
            message = f"{resolved.name} 检查完成，发现异常：{inspection.anomalies}"
        else:
            message = f"{resolved.name} 检查完成，未发现异常。"
        await ctx.report.say(message)

        return {"success": True, "inspection": inspection.to_dict()}

    except SafetyRejectedError as exc:
        await ctx.robot.stop(reason=f"safety_rejected:{exc.code}")
        await ctx.report.say(f"任务被安全系统拒绝：{exc.code}")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except SkillTimeoutError as exc:
        await ctx.robot.stop(reason=f"timeout:{exc.code}")
        await ctx.report.say("任务超时，已请求停止。")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
    except AgenticRuntimeError as exc:
        await ctx.report.say(f"任务失败：{exc.code}")
        return {"success": False, "error_code": exc.code, "reason": exc.message}
```

对应 `app.yaml` 权限：

```yaml
name: my_room_inspector
version: 0.1.0
description: Inspect a named room through Agentic OS APIs.
entrypoint: main:run
permissions:
  - robot.state.read
  - robot.move
  - robot.stop
  - world.read
  - perception.inspect
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
  - human.ask
  - report.say
safety_policy:
  allow_autonomous_navigation: true
  allow_manipulation: false
  require_human_confirmation_for:
    - navigation
  forbidden_zones:
    - stairs
  max_task_duration_s: 300
runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 1
  max_memory_write_per_task: 20
  llm_planning_enabled: false
```

## 12. 常见应用模式

### 12.1 巡检

推荐流程：

```text
resolve_place -> get_state -> navigate_to -> inspect_area -> remember -> report.say
```

要点：

- 先解析地点，不要直接把用户文本当作机器人目标。
- 检查 `PlaceRef.allowed` 和 `RobotState.estop_pressed`。
- `inspect_area` 失败时不要生成“未发现异常”的成功报告。

### 12.2 定点导航

推荐只接受地点名或经过 `resolve_place` 的地点，不接受坐标或速度命令。若目标无法解析，返回 `PLACE_NOT_FOUND`；若目标是禁区，返回 `FORBIDDEN_ZONE`。

### 12.3 人工确认后执行

危险动作前使用 `ctx.human.ask()` 或依赖 Runtime operator intervention。`human.ask` 自身也是受权限和 intervention 管控的能力，不能把它当作本地 input prompt。

### 12.4 记忆读写

用 `ctx.memory.remember(key, value)` 记录任务摘要、上次地点、inspection 结果等。不要把密钥、原始大图、视频或不可审计的私人数据写入 memory。读取时给 `default`：

```python
last = await ctx.memory.recall("last_inspection", default={})
```

### 12.5 失败降级

失败降级必须保持真实：

- Bridge 不可用：返回 `ROS_BRIDGE_UNAVAILABLE`，不要伪造机器人已到达。
- LLM 不可用：返回 LLM 错误，不切到成功的本地关键词 planner。
- Human timeout：返回 `HUMAN_OPERATOR_TIMEOUT`，不要自动当作 yes。
- Inspection 失败：报告检查失败，不写“未发现异常”。

### 12.6 停止/取消

在导航、检查、机械臂动作出现异常或用户取消时调用：

```python
await ctx.robot.stop(reason="operator_cancelled")
```

`robot.stop` 会取消当前 session 的 active calls，并调用 safety stop backend。即使 stop backend 缺失，也会写结构化失败和 audit。

## 13. Agent App 测试指南

### 13.1 Manifest 测试

```python
from pathlib import Path

import yaml


def test_manifest_declares_capabilities():
    data = yaml.safe_load((Path(__file__).parents[1] / "app.yaml").read_text(encoding="utf-8"))
    assert data["entrypoint"] == "main:run"
    assert "robot.navigate_to" in data["required_capabilities"]
    assert "robot.move" in data["permissions"]
```

### 13.2 禁止 ROS2 调用

仓库级检查：

```bash
python scripts/check_agentic_app_boundaries.py agentic_apps
```

测试中也可以检查应用源码不含 `rclpy`、`/cmd_vel`、`NavigateToPose`、`MoveGroup` 等模式。

### 13.3 使用记录型 executor 测 SDK 编排

```python
import asyncio

from agentic_runtime.sdk import AgentContext
from agentic_runtime.types import AppManifest, SkillResult


class RecordingExecutor:
    kernel_service = None

    def __init__(self):
        self.calls = []

    async def execute(self, app, name, args, session_id, **kwargs):
        self.calls.append((name, args))
        if name == "world.resolve_place":
            return SkillResult(success=True, data={"place": {"id": "kitchen", "name": "厨房", "frame_id": "map", "pose": {}, "allowed": True}})
        if name == "robot.get_state":
            return SkillResult(success=True, data={"state": {"robot_id": "r1", "mode": "idle", "battery_state": "ok", "battery_percent": 80, "is_localized": True, "is_moving": False, "estop_pressed": False}})
        return SkillResult(success=True, data={})


def test_app_flow():
    async def scenario():
        app = AppManifest("test_app", "0", "", "main:run", ["world.read", "robot.state.read"], [])
        executor = RecordingExecutor()
        ctx = AgentContext(executor, app, "sess_test")
        await ctx.world.resolve_place("厨房")
        await ctx.robot.get_state()
        return executor.calls

    calls = asyncio.run(scenario())
    assert calls[0][0] == "world.resolve_place"
```

### 13.4 权限失败场景

用真实 `SkillExecutor` 或 RuntimeServer test setup 构造缺少权限的 app manifest，断言 backend 没有被调用，错误码为 `PERMISSION_DENIED`。

### 13.5 Bridge 缺失场景

测试应确认没有 ROS2 CLI/bridge 时返回 `ROS_BRIDGE_UNAVAILABLE`，并且应用不会返回成功。仓库测试中的 `create_test_runtime_server()` 使用替代 runner 让 `ros2` 命令失败，适合参考。

### 13.6 Human queue 场景

测试应覆盖：

- 没有 operator response 时返回 `HUMAN_OPERATOR_TIMEOUT`。
- 外部写 response 后返回 `answered=True`。
- 取消时返回 `HUMAN_CANCELLED`。

### 13.7 运行应用测试

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/my_agent/tests
scripts/verify_agentic_app_tutorials.sh
```

## 14. 兼容性与扩展

### 14.1 Stable Foundation surface

当前通用 stable surface 是：

```python
ctx.robot.get_state()
ctx.robot.navigate_to(place)
ctx.robot.inspect_area(place)
ctx.robot.stop()
ctx.world.resolve_place(name)
ctx.memory.remember(key, value)
ctx.memory.recall(key)
ctx.human.ask(question)
ctx.report.say(message)
```

这些 API 是普通应用的首选接口。

### 14.2 Current specialized surface

这些能力当前已实现但更依赖具体应用、真实 bridge 或 provider 配置：

- `ctx.llm.chat_json`
- `ctx.perception.observe`
- `ctx.perception.capture_photo`
- `ctx.arm.get_state`
- `ctx.arm.move_named`
- `ctx.gripper.open/close/set`
- `ctx.storage.list_recent_photos`
- `ctx.kernel.*`
- color-block 和 manipulation skill

使用它们时，要在 `app.yaml` 中声明对应权限和 capability，并为缺失真实依赖写失败测试。

### 14.3 Internal or not for app dependency

应用不要依赖：

- `agentic_runtime.server.RuntimeServer` 内部装配细节。
- `SkillExecutor`、`SkillDispatcher`、`ResourceManager`、bridge client 的内部方法。
- `agentic_os.kernel.*` manager 内部类，除非通过 `ctx.kernel` SDK facade。
- `ros2_bridge_src/*` Python 模块。
- `/opt/agentic/var` 内部文件格式，除非文档明确说明为 audit/report/session JSONL 查询接口。

### 14.4 Planned / reserved / unsupported

| 能力 | 当前状态 |
| --- | --- |
| `ctx.world.get_places()` | SDK 中存在占位，当前返回空列表；unsupported for app logic。 |
| `ctx.world.locate_user()` | SDK 中存在占位，当前返回 `None`；unsupported。 |
| ROS bridge `service`、`action`、`topic`、`http`、`websocket` mode | classified unsupported/reserved；当前可用 real mode 是 `cli` 且需要 `ros2` CLI。 |
| Human `console`、`http`、`websocket` provider | reserved；当前实现是 `file_queue`。 |
| Memory/storage semantic vector provider | reserved；当前 memory 是 SQLite/FTS style path，storage 是 local FS/SQLite path。 |
| Tool MCP provider | reserved；当前 tool provider 是 builtin。 |
| Production offline success backend | unsupported；缺失真实依赖必须返回结构化失败。 |
| 直接坐标导航、实时速度控制、多机器人调度、App Store、复杂 VLM 深度推理 | 不属于当前应用接口。 |

## 15. FAQ 与反模式

**Q: 我可以在 Agent App 里 `import rclpy` 吗？**
不可以。只有 ROS2 bridge package 可以 import `rclpy`。应用必须调用 `ctx.*`。

**Q: 我只想发一下 `/cmd_vel`，可以吗？**
不可以。底盘移动必须通过 `ctx.robot.navigate_to()` 或未来明确授权的高层 motion capability，并经过权限、锁、安全和审计。

**Q: 可以直接调用 Nav2 `NavigateToPose` 或 MoveIt `MoveGroup` 吗？**
不可以。Agent App 不直接调用 Nav2/MoveIt action。bridge 层负责适配。

**Q: 没有真实机器人时能跑成功 demo 吗？**
当前不能跑机器人成功路径。没有真实 ROS2 bridge 时应看到 `ROS_BRIDGE_UNAVAILABLE` 或相关结构化错误。你可以用单元测试验证编排、权限失败、错误处理、memory/report 和 human timeout。

**Q: `ctx.robot.navigate_to()` 返回 `success=False` 还是抛异常？**
当前高层 SDK 会在失败时抛 `AgenticRuntimeError` 或子类。成功时才返回 dataclass 或 `SkillResult`。

**Q: LLM 可以直接控制机器人吗？**
不可以。LLM 只能生成计划或结构化意图；应用必须做 deterministic schema/policy validation，机器人动作仍通过 SDK/Runtime。

**Q: 我可以在失败时写一个本地成功结果吗？**
不可以。缺失 bridge、LLM、human、camera、arm、gripper 或 verifier 时必须返回稳定错误码，不能编造 evidence、导航成功、检查正常或抓取成功。

**Q: 为什么 human ask 也会被 access/intervention 拒绝？**
当前 Kernel 把人机介入也作为高风险流程管理。默认 intervention provider 是 deny-by-default；部署或测试需要显式配置允许的 intervention provider。

**Q: 我能通过 `ctx.kernel.tool.call("robot.navigate_to", ...)` 绕过限制吗？**
不能。工具系统会拒绝机器人 capability，错误码是 `TOOL_FORBIDDEN_ROBOT_CAPABILITY`。

**Q: 应用可以直接读 `/opt/agentic/var/audit/audit.jsonl` 吗？**
调试时可以查看 audit；应用逻辑不应依赖未文档化的内部文件布局。优先通过 CLI/session/audit 接口理解运行结果。

**常见反模式：**

- 把 Agent App 做成 ROS2 node。
- 在应用里创建 publisher/subscription/action client。
- 在应用里读 `/scan`、`/odom`、`/tf`。
- 用 LLM 生成速度、力矩、关节或底盘实时控制命令。
- 遇到 `ROS_BRIDGE_UNAVAILABLE` 后返回成功。
- 不声明权限却调用机器人动作。
- 忽略 `AgenticRuntimeError`，导致异常冒泡成 `APP_EXCEPTION`。
- 把真实照片、视频、audit、task log 或 secret 提交到 git。
