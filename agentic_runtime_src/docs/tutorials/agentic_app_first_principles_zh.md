# Agentic App 第一性原理开发教程

本文面向在 Agentic OS ROS 上开发 Agent App 的应用开发者。它不从 ROS2 node、topic、action 或硬件驱动开始，而是从一个更底层的问题开始：

> 当软件能够影响真实机器人时，应用代码应该拥有什么权力，又必须放弃什么权力？

Agentic App 的答案是：应用只表达任务意图和业务编排；权限、安全、资源互斥、真实能力调用和审计归 Agentic Runtime / Kernel 所有；ROS2 细节只存在于 AgenticOS-owned bridge 层。

## 1. 从第一性原理看 Agentic App

真实机器人应用有三个不可回避的事实。

第一，机器人动作会改变物理世界。一次导航、抓取或停止不是普通函数调用，而是对空间、人员、设备和任务状态的影响。因此应用不能直接拥有底盘速度、Nav2 goal、MoveIt action、传感器 topic 或驱动接口。

第二，Agent 逻辑不是实时控制器。LLM、规划器、业务规则和人机交互适合做任务级决策，不适合做毫秒级闭环控制。实时控制仍应由 ROS2 controller、Nav2、MoveIt 或厂商驱动完成。

第三，可审计性比“能跑起来”更重要。系统必须能回答：谁请求了动作、请求了什么、用什么权限、占用了哪个资源、哪个安全检查允许了它、失败时返回了什么结构化错误。

由此推出 Agentic App 的编程模型：

```text
User intent
  -> Agent App task orchestration
  -> high-level Agentic SDK capability request
  -> Runtime permission check
  -> resource lock / lifecycle / safety guard
  -> audited capability execution
  -> AgenticOS ROS2 bridge
  -> ROS2 / robot hardware
```

所以 Agentic App 不是 ROS2 包，不是 bridge node，不是 LLM wrapper，也不是硬件适配器。它是运行在 Runtime 之上的任务编排代码。

## 2. 最小心智模型

把每个 Agent App 看成一个“受限进程”：

| 问题 | Agentic App 的答案 |
| --- | --- |
| 我是谁？ | `app.yaml` 中的 `name`、`version`、`entrypoint`。 |
| 我被允许做什么？ | `permissions`。 |
| 我依赖哪些系统能力？ | `required_capabilities`。 |
| 我怎样影响机器人？ | 只能调用 `ctx.robot.*` 等高层 SDK。 |
| 我怎样处理不确定性？ | 先向 Runtime 或人确认，再执行；失败返回结构化错误。 |
| 我怎样证明发生了什么？ | 返回 `syscall_id`、`audit_id`、步骤结果、错误码和证据路径。 |

可用的 foundation API 是：

```python
await ctx.robot.get_state()
await ctx.robot.navigate_to(place)
await ctx.robot.inspect_area(place)
await ctx.robot.stop()
await ctx.world.resolve_place(name)
await ctx.memory.remember(key, value)
await ctx.memory.recall(key)
await ctx.human.ask(question)
await ctx.report.say(message)
```

原则是：应用描述“去厨房检查”，而不是描述“发布速度、订阅里程计、发送 Nav2 action”。

## 3. 设计一个 Agent App 的五步法

### Step 1: 把用户需求翻译成任务目标

不要一上来写代码。先写清楚应用承诺完成的结果，例如：

```text
用户说：“去厨房看看有没有异常。”

Agent App 目标：
1. 解析“厨房”为 Runtime 认识的地点。
2. 读取机器人状态，确认可以执行任务。
3. 请求 Runtime 导航到厨房。
4. 请求 Runtime 执行区域检查。
5. 记录检查结果。
6. 向用户报告完成或失败原因。
```

这里没有 ROS2 topic、底盘速度、相机订阅或 Nav2 action，因为这些不是应用层概念。

### Step 2: 列出风险和资源

任何会动机器人的步骤都要先问：

| 步骤 | 风险 | 应用层动作 |
| --- | --- | --- |
| 解析地点 | 地点不存在或禁区 | 使用 `ctx.world.resolve_place()`，失败即停止流程。 |
| 导航 | 机器人移动、占用运动资源 | 使用 `ctx.robot.navigate_to()`，由 Runtime 做权限、安全和资源锁。 |
| 检查区域 | 访问感知能力和环境证据 | 使用 `ctx.robot.inspect_area()`，不要直接订阅传感器。 |
| 异常处理 | 运动未完成或任务被取消 | 使用 `ctx.robot.stop()` 请求 Runtime 安全停止。 |

这一步决定 manifest 里需要什么权限，也决定测试要覆盖哪些失败路径。

### Step 3: 写 manifest，而不是偷偷调用能力

从模板创建应用：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/create_agentic_app.py kitchen_inspector_agent
```

`agentic_apps/kitchen_inspector_agent/app.yaml` 可以按这个形状声明：

```yaml
name: kitchen_inspector_agent
version: 0.1.0
description: Inspect a named place through Agentic Runtime capabilities.
entrypoint: main:run
permissions:
  - robot.state.read
  - robot.move
  - robot.inspect
  - robot.stop
  - world.read
  - memory.write
  - memory.read
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
safety_policy:
  allow_autonomous_navigation: true
  allow_manipulation: false
  require_human_confirmation_for:
    - robot.navigate_to
  forbidden_zones: []
  max_task_duration_s: 180
runtime_limits:
  max_concurrent_tasks: 1
  max_retries_per_skill: 0
  max_memory_write_per_task: 4
  llm_planning_enabled: false
```

第一性原理解释：

- `permissions` 是应用“被授予的权力”。
- `required_capabilities` 是应用“期待 Runtime 提供的能力”。
- `safety_policy` 是应用“对风险的声明”，最终强制仍由 Runtime / safety guard / skill manifest 完成。
- `runtime_limits` 是应用“愿意消耗多少系统资源”的上限。

### Step 4: 入口代码只做任务编排

`main.py` 的入口固定是：

```python
from __future__ import annotations

from typing import Any

from agentic_runtime.errors import AgenticRuntimeError
from agentic_runtime.sdk import AgentContext


async def run(ctx: AgentContext, **kwargs: Any) -> dict[str, Any]:
    place_name = str(kwargs.get("place") or "厨房").strip()
    steps: list[dict[str, Any]] = []
    motion_started = False

    try:
        place = await ctx.world.resolve_place(place_name)
        steps.append(_step("resolve_place", place))

        state = await ctx.robot.get_state()
        steps.append(_step("get_state", state))

        confirm = await ctx.human.ask(
            f"确认让机器人前往 {place_name} 并执行检查吗？",
            options=["CONFIRM", "CANCEL"],
            timeout_s=60,
            require_confirmation=True,
        )
        steps.append(_step("human_confirm", confirm))
        if getattr(confirm, "answer", "") != "CONFIRM":
            return _result(False, "OPERATOR_CANCELLED", "operator cancelled navigation", steps)

        nav = await ctx.robot.navigate_to(place_name, timeout_s=120)
        motion_started = True
        steps.append(_step("navigate_to", nav))

        inspection = await ctx.robot.inspect_area(place_name, timeout_s=60)
        steps.append(_step("inspect_area", inspection))

        await ctx.memory.remember(
            f"inspection:{place_name}",
            {
                "place": place_name,
                "inspection": _payload(inspection),
            },
        )

        report = await ctx.report.say(f"{place_name} 检查完成。")
        steps.append(_step("report", report))
        return _result(True, "", "", steps)

    except AgenticRuntimeError as exc:
        if motion_started:
            stop = await ctx.robot.stop(reason=f"kitchen_inspector_error:{exc.code}")
            steps.append(_step("stop_after_error", stop))
        return _result(False, exc.code, exc.message, steps)


def _step(name: str, value: Any) -> dict[str, Any]:
    return {
        "name": name,
        "success": bool(getattr(value, "success", True)),
        "error_code": str(getattr(value, "error_code", "") or ""),
        "reason": str(getattr(value, "reason", "") or ""),
        "syscall_id": str(getattr(value, "syscall_id", "") or ""),
        "audit_id": str(getattr(value, "audit_id", "") or ""),
        "data": _payload(value),
    }


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {"value": data}
    data = getattr(value, "data", None)
    if isinstance(data, dict):
        return data
    return {}


def _result(success: bool, error_code: str, reason: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "success": success,
        "error_code": error_code,
        "reason": reason,
        "steps": steps,
        "syscall_ids": [step["syscall_id"] for step in steps if step.get("syscall_id")],
        "audit_ids": [step["audit_id"] for step in steps if step.get("audit_id")],
    }
```

这个例子体现了几条核心规则：

- App 不导入 `rclpy`。
- App 不发布机器人底层 topic。
- App 不直接调用 Nav2 或 MoveIt。
- App 不实现实时控制循环。
- 运动失败后通过 `ctx.robot.stop()` 请求 Runtime 处理停止。
- 返回值包含 `success`、`error_code`、`reason`、步骤和审计线索。

### Step 5: 测试边界，而不只测试 happy path

Agentic App 至少要测四类事情：

| 测试 | 目的 |
| --- | --- |
| manifest 测试 | `entrypoint`、`permissions`、`required_capabilities` 与代码行为一致。 |
| 边界测试 | 应用代码没有 ROS2 import、底层 topic、Nav2/MoveIt 直连。 |
| 失败测试 | 地点解析失败、权限不足、bridge 缺失、operator 取消时返回结构化错误。 |
| smoke 测试 | 在 Runtime 或 Kernel 路径下验证入口能被加载和执行。 |

常用命令：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
python scripts/check_agentic_app_uses_template.py agentic_apps/kitchen_inspector_agent
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_apps/kitchen_inspector_agent/tests
```

仓库级检查：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
scripts/run_tests.sh
scripts/verify_foundation.sh
scripts/verify_capability_truth.sh
scripts/verify_no_fake_mock.sh
```

测试替身只应该存在于测试中，用来验证应用逻辑如何响应 Runtime 返回；它不能成为生产 Runtime 的成功后端。真实依赖缺失时，应返回 `ROS_SERVICE_UNAVAILABLE`、`ROS_ACTION_UNAVAILABLE`、`SKILL_BACKEND_UNAVAILABLE` 或 `UNVERIFIED_REAL_DEPENDENCY` 这类稳定错误，而不是把任务标记为成功。

## 4. 如果应用需要 LLM

LLM 在 Agentic App 里只能做“任务理解和计划草案”，不能直接执行机器人动作。

正确形状：

```python
plan_result = await ctx.llm.chat_json(
    system_prompt=system_prompt,
    user_prompt=f"User task: {task_text}",
    timeout_s=20,
)
```

然后应用必须做确定性校验：

1. JSON 字段是否完整。
2. `schema_version` 是否匹配。
3. 动作步骤是否在允许列表内。
4. 目标地点、颜色、对象、风险等级是否合法。
5. 是否需要 `ctx.human.ask()`。
6. manifest 是否声明了所需权限和 capability。

不要让 LLM 输出变成“隐式权限”。LLM 说要导航，不代表应用已经被授权导航；仍然必须走 `ctx.robot.navigate_to()`，并由 Runtime 检查权限、资源、安全和审计。

## 5. 错误处理原则

Agentic App 不应该抛出散乱异常给用户。它应该把失败折叠成稳定结构：

```json
{
  "schema_version": "1.0",
  "success": false,
  "error_code": "ROS_ACTION_UNAVAILABLE",
  "reason": "navigation bridge is unavailable",
  "steps": [],
  "syscall_ids": [],
  "audit_ids": [],
  "next_action": "Start the AgenticOS capability bridge and rerun."
}
```

实践规则：

- 输入缺失：返回 `*_INPUT_REQUIRED` 或具体业务错误。
- LLM 不可用：返回 `LLM_PROVIDER_UNCONFIGURED` 或 Runtime 给出的错误码。
- 权限不足：返回 Runtime 给出的 `PERMISSION_DENIED` 或 access 错误。
- 真实 bridge 不存在：返回 `ROS_SERVICE_UNAVAILABLE` 或 `ROS_ACTION_UNAVAILABLE`。
- 动作超时：优先请求 `ctx.robot.stop()`，再返回超时错误。
- 真实依赖未经验证：返回 `UNVERIFIED_REAL_DEPENDENCY`，不要继续伪装成功。

## 6. 判断一个设计是否是 Agentic App

可以用这组问题自检：

| 问题 | 合格答案 |
| --- | --- |
| 业务代码是否只表达任务级意图？ | 是，调用 `ctx.*` 高层 API。 |
| 机器人动作是否都经过 Runtime？ | 是，移动、检查、停止都走 SDK。 |
| 是否声明了权限和能力？ | 是，在 `app.yaml` 中声明。 |
| 是否能审计每个危险动作？ | 是，返回或记录 `audit_id` / `syscall_id`。 |
| 是否避免实时闭环控制？ | 是，App 不做底层控制循环。 |
| 真实依赖缺失时是否失败？ | 是，返回结构化错误。 |
| 测试是否覆盖边界和失败？ | 是，不只覆盖成功路径。 |

如果某个设计需要直接写 ROS2 node、订阅传感器 topic、发布速度、调用 Nav2/MoveIt action 或导入机器人驱动，那它不是 Agentic App；它应该被拆到 AgenticOS bridge/HAL 层，或者变成 Runtime 管理的 system skill 后端。

## 7. 答辩级案例：红色物块从一句话到夹爪闭合的完整链路

这一节按一次真实请求讲到函数、字段、公式和参数。假设用户输入：

```text
把红色物块夹起来，保持夹住。
```

导师如果问“到底怎么夹起来”，不要回答“调用一个能力”。要按下面这条链路讲：

```text
main.py 状态机
  -> Runtime skill call
  -> ROS2 service/action contract
  -> inspection_bridge_node.py 视觉检测与对中
  -> manipulation_bridge_node.py 坐标变换、IK、servo pulse
  -> inspection_bridge_node.py 夹持验证
  -> App 根据验证证据决定 success
```

### 7.1 第一层：LLM 只产出计划，不产出控制量

入口是 `agentic_apps/color_block_grasper_agent/main.py::run()`。

`run()` 先从 `task_text/message/text` 取自然语言。空输入立即失败：

```text
error_code = COLOR_BLOCK_LLM_PLAN_REQUIRED
```

然后 `_plan_with_system_llm()` 调用：

```python
await ctx.llm.chat_json(
    system_prompt=_system_prompt(),
    user_prompt=f"User task: {task_text}",
    timeout_s=30,
)
```

LLM 必须返回一个 JSON object。它不能返回“servo1=500”这种底层控制量。它只能返回任务计划字段：

```json
{
  "schema_version": "1.0",
  "planner_mode": "llm",
  "target_color": "red",
  "place_target": "hold_position",
  "requires_manipulation": true,
  "needs_confirmation": true,
  "steps": [
    "prepare_arm_pose",
    "center_color_block",
    "detect_color_block",
    "capture_evidence",
    "pick_color_block",
    "reset_arm_home_holding_gripper",
    "post_pick_verify",
    "place_color_block"
  ],
  "risk_class": "controlled_manipulation",
  "user_summary": "Pick and hold the red color block."
}
```

`_validate_plan()` 逐项卡死：

| 字段 | 约束 | 不满足时 |
| --- | --- | --- |
| `schema_version` | 必须是 `1.0` | `COLOR_BLOCK_LLM_PLAN_INVALID` |
| `planner_mode` | 必须是 `llm` | `COLOR_BLOCK_LLM_PLAN_INVALID` |
| `target_color` | 必须在 `red/green/blue/yellow` | `COLOR_BLOCK_LLM_PLAN_INVALID` |
| `requires_manipulation` | 必须是 `true` | `COLOR_BLOCK_LLM_PLAN_INVALID` |
| `needs_confirmation` | 必须是 bool，且后续策略要求为 `true` | `COLOR_BLOCK_LLM_PLAN_INVALID` |
| `steps` | 必须完全等于固定 8 步 | `COLOR_BLOCK_LLM_PLAN_INVALID` |
| `risk_class` | 只能是 `controlled_manipulation` 或 `manipulation_real_hardware` | `COLOR_BLOCK_LLM_PLAN_INVALID` |

这一步的第一性原理是：LLM 只能做语义解析，不能获得机器人执行权。

### 7.2 第二层：App 状态机逐步调用 Runtime skill

`run()` 不是自由规划器，而是固定状态机。每一步失败都会停止向后执行：

| 顺序 | App 函数 | Runtime skill | 作用 |
| --- | --- | --- | --- |
| 1 | `_record_start()` | `kernel.context.put`, `kernel.storage.write` | 保存任务上下文和开始记录 |
| 2 | `_confirm_manipulation()` | `human.ask` | 人确认真实抓取 |
| 3 | `_check_readiness()` | `robot.get_state`, `arm.get_state` | 检查机器人、机械臂、夹爪后端 |
| 4 | `_prepare_arm_pose()` | `arm.move_named` with `arm_home` | 进入初始安全姿态 |
| 5 | `_center_color_block()` | `perception.center_color_block` | 低速视觉对中 |
| 6 | `_detect_color_block()` | `perception.detect_color_block` | 获得颜色块 2D/3D 检测 |
| 7 | `_capture_evidence()` | `perception.capture_photo` | 保存抓取前图像证据 |
| 8 | `_pick_color_block()` | `manipulation.pick_color_block` | 规划并执行抓取 |
| 9 | `_reset_arm_home_holding_gripper()` | `arm.move_named` with `arm_home` | 回到验证姿态 |
| 10 | `_post_pick_verify()` | `arm.get_state`, `capture_photo`, `verify_held_color_block` | 验证确实夹住 |
| 11 | `_place_color_block()` | `manipulation.place_color_block` | 放置或保持夹持 |
| 12 | `_finish_success()` | `kernel.memory.remember`, `kernel.storage.write`, `report.say` | 写结果和报告 |

App 权限由 `app.yaml` 声明，策略校验要求这些 permission 存在：

```text
perception.detect.color_block
perception.center.color_block
perception.capture
perception.verify.color_block_held
manipulation.pick.color_block
manipulation.place.color_block
human.ask
```

没有这些权限时，App 返回：

```text
COLOR_BLOCK_CAPABILITY_UNAVAILABLE
```

### 7.3 第三层：Runtime skill 到 ROS2 contract 的具体接口

App 调用的是 `ctx.kernel.skill.call()`，不是 ROS2。Runtime 根据 system skill manifest 转成 bridge 调用。

本案例关键 ROS2 contract 是：

```text
/agentic/perception/center_color_block
request:  color, target, evidence_label, request_id, timeout_s
response: success, error_code, reason, alignment_json, evidence_json

/agentic/perception/detect_color_block
request:  color, target, evidence_label, request_id, timeout_s
response: success, error_code, reason, detection_json, evidence_json

/agentic/manipulation/pick_color_block
goal:     color, target, detection_json, evidence_json, request_id, timeout_s
result:   success, error_code, reason, result_json
feedback: status, progress, feedback_json

/agentic/perception/verify_held_color_block
request:  color, target, detection_json, pick_result_json, evidence_label, request_id, timeout_s
response: success, error_code, reason, verified_held, verification_json, evidence_json

/agentic/manipulation/place_color_block
goal:     color, place_target, pick_result_json, request_id, timeout_s
result:   success, error_code, reason, result_json
feedback: status, progress, feedback_json
```

导师问“App 怎么保证不绕过安全”，答：

1. App 只发 skill name 和 JSON args。
2. Runtime 检查 manifest permission。
3. Skill manifest 声明 resource locks，例如 `camera`、`arm`、`gripper`、`manipulation_backend`。
4. Safety guard 检查 E-stop、named action allowlist、timeout、workspace 和 gripper allowlist。
5. Bridge 才接触 ROS2 topic/action/service。
6. 每一步都有 syscall/audit/evidence。

### 7.4 第四层：视觉检测到底怎么找到红块

代码位置：

```text
ros2_bridge_src/agentic_capability_bridge/agentic_capability_bridge/inspection_bridge_node.py
  _detect_color_block()
  _segment_color()
  _estimate_depth()
  _depth_pixel_to_camera()
```

输入 topic 来自 profile：

| 数据 | topic |
| --- | --- |
| RGB | `/depth_cam/rgb0/image_raw`，fallback `/camera/color/image_raw` |
| Depth | `/depth_cam/depth0/image_raw`，fallback `/camera/depth/image_raw` |
| CameraInfo | `/depth_cam/depth0/camera_info`、`/camera/color/camera_info`、`/depth_cam/rgb0/camera_info` |
| 新鲜度 | `frame_freshness_s = 5.0` |

没有 fresh RGB，返回 `CAMERA_UNAVAILABLE`。
没有 fresh depth，返回 `DEPTH_UNAVAILABLE`。
没有 fresh CameraInfo，返回 `CAMERA_INFO_UNAVAILABLE`。

红色阈值来自 `agentic_runtime_src/configs/robot_profiles/rosorin_arm_camera.yaml`：

```yaml
red:
  min: [0, 152, 108]
  max: [255, 255, 255]
```

具体视觉 pipeline：

```text
ROS Image
  -> 按 encoding 转 OpenCV BGR
  -> resize 到 1/2
  -> GaussianBlur(kernel=3x3, sigma=3)
  -> BGR2LAB
  -> inRange(LAB, red_min, red_max)
  -> erode(3x3)
  -> dilate(3x3)
  -> findContours(RETR_EXTERNAL)
  -> contourArea * 4.0
  -> minEnclosingCircle
  -> ROI 过滤
  -> 选面积最大候选
```

ROI 和候选过滤：

```text
detect_roi_x_min_ratio 默认 0.0
detect_roi_x_max_ratio = 0.78
detect_roi_y_min_ratio = 0.08
detect_roi_y_max_ratio 默认 1.0
min_area_px = 50
```

所以红块中心必须满足：

```text
0 <= center_x <= 0.78 * image_width
0.08 * image_height <= center_y <= image_height
area_px >= 50
```

深度估计：

```text
roi_radius = max(5 px, round(color_radius_px * 1.0))
depth_m = mean(valid_depth_roi)
depth_m += 0.02   # object_radius_compensation_m
depth_m += 0.025  # depth_error_compensation_m
if depth_m > 0.38: reject
```

`16UC1` depth 会从毫米转米；`32FC1` 直接按米处理。

像素反投影公式：

```text
X_camera = (u - cx) * Z / fx
Y_camera = (v - cy) * Z / fy
Z_camera = depth_m
```

`fx, fy, cx, cy` 来自 `CameraInfo.k`。最终 detection 输出类似：

```json
{
  "detection_id": "det_...",
  "color": "red",
  "target": "workspace",
  "confidence": 0.37,
  "frame_id": "...",
  "center_px": [400.0, 360.0],
  "radius_px": 28.0,
  "area_px": 2463.0,
  "depth_m": 0.30,
  "camera_position_m": [0.04, 0.06, 0.30],
  "evidence_image_path": "/opt/agentic/var/evidence/color_block/...",
  "evidence_metadata_path": "/opt/agentic/var/evidence/color_block/..."
}
```

上面的数值是讲解用例。真实值来自当前 camera frame、depth frame 和 CameraInfo。

### 7.5 第五层：视觉对中到底怎么调舵机

对中 service 是 `/agentic/perception/center_color_block`，内部函数 `_center_color_block()`。

参数：

```yaml
center_target_x_ratio: 0.52
center_target_y_ratio: 0.78
center_tolerance_ratio: 0.045
center_base_start_pulse: 500
center_pitch_start_pulse: 188
center_base_pulse_limits: [440, 560]
center_pitch_pulse_limits: [120, 260]
center_base_gain: -100.0
center_pitch_gain: 50.0
center_max_servo_step: 8
center_max_iterations: 18
center_servo_duration_s: 0.08
center_settle_s: 0.20
```

每轮重新拍一帧，重新做 LAB 分割，得到候选中心 `(u, v)`。

误差定义：

```text
dx = u / image_width  - 0.52
dy = v / image_height - 0.78
```

停止条件：

```text
abs(dx) <= 0.045 and abs(dy) <= 0.045
```

控制量：

```text
base_delta  = clip(dx  * -100.0, -8, 8)
pitch_delta = clip(-dy *   50.0, -8, 8)
```

更新 pulse：

```text
base_pulse  = clip(base_pulse  + base_delta,  440, 560)
pitch_pulse = clip(pitch_pulse + pitch_delta, 120, 260)
```

发布到 `/servo_controller`：

```text
ServosPosition:
  duration = 0.08
  position_unit = "pulse"
  position = [
    {id: 1, position: base_pulse},
    {id: 4, position: pitch_pulse}
  ]
```

具体演算例子：

```text
image_width = 640
image_height = 480
检测中心 u=400, v=410
target pixel = (0.52*640, 0.78*480) = (332.8, 374.4)

dx = 400/640 - 0.52 = 0.105
dy = 410/480 - 0.78 = 0.074

base_delta = clip(0.105 * -100, -8, 8) = -8
pitch_delta = clip(-0.074 * 50, -8, 8) = -3

base_pulse: 500 -> 492
pitch_pulse: 188 -> 185
```

对中最多 `18` 轮。没有 servo subscriber 返回 `COLOR_BLOCK_ALIGNMENT_UNAVAILABLE`；超时未对中返回 `COLOR_BLOCK_ALIGNMENT_FAILED`。

### 7.6 第六层：检测结果怎么变成机械臂抓取点

抓取 action 是 `/agentic/manipulation/pick_color_block`，内部函数：

```text
ManipulationBridgeNode.execute_pick_color_block()
  -> _plan_color_block_pick()
  -> _camera_to_arm_position()
  -> _solve_ik()
  -> _execute_pick_motion()
```

`execute_pick_color_block()` 先检查：

```text
detection_json 必须是 JSON object
detection.color 必须等于 request.color
detection.camera_position_m 必须是长度 >= 3 的 list
gripper backend 必须有 subscriber
/kinematics/get_current_pose 必须可用
/kinematics/set_pose_target 必须可用
当前没有 active arm action
```

任一不满足就不动机械臂。

坐标变换分三步。

第一，读取当前末端位姿：

```text
/kinematics/get_current_pose -> pose
pose -> 4x4 endpoint_matrix
```

第二，构造手眼矩阵。配置是：

```yaml
hand2cam_tx_m: -0.101
hand2cam_ty_m: 0.0
hand2cam_tz_m: 0.037
```

代码中的矩阵是：

```text
T_hand_camera =
[[ 0,  0,  1, tx],
 [-1,  0,  0, ty],
 [ 0, -1,  0, tz],
 [ 0,  0,  0,  1]]
```

第三，把相机坐标的目标点变成机械臂坐标：

```text
T_camera_object = identity with translation camera_position_m
T_arm_object = T_world_hand @ T_hand_camera @ T_camera_object
arm_position = translation(T_arm_object)
```

然后加抓取补偿：

```text
pick_x = arm_x + 0.012
pick_y = arm_y + 0.027
pick_z = arm_z + 0.094
```

工作空间检查：

```yaml
x: [0.12, 0.32]
y: [-0.18, 0.18]
z: [0.03, 0.36]
```

如果 `pick_x/pick_y/pick_z` 超出范围，抛错并返回 `COLOR_BLOCK_PICK_FAILED`。不会尝试硬抓。

抓取俯仰角选择：

```text
if pick_z < 0.20:
    pitch = 76.0
else:
    pitch = 30.0
```

IK 求三组 pulse：

```text
pick_position     = [pick_x, pick_y, pick_z]
pregrasp_position = [pick_x, pick_y, pick_z + 0.04]
lift_position     = [pick_x, pick_y, pick_z + 0.08]
```

调用：

```text
/kinematics/set_pose_target(
  position_m,
  pitch,
  pitch_range=[-180.0, 180.0],
  pitch_resolution=1.0
)
```

返回必须包含至少 5 个 pulse，分别用于 servo 1 到 5。失败就返回：

```text
IK failed for position=... pitch=...
```

这就是为什么不能说“Agent App 算了关节角”。准确说法是：

> bridge 把视觉 3D 点转换到机械臂坐标，调用已有 kinematics service 求 IK，IK 输出 servo pulse；Agent App 只等待结构化结果。

### 7.7 第七层：真实抓取动作的 pulse/时长序列

当前 profile 写的是：

```yaml
pick_execution_strategy: ik_color_block_pick
gripper_open: 150
gripper_close: 650
pick_move_duration_s: 2.6
pick_settle_s: 3.2
```

因为策略是 `ik_color_block_pick`，所以使用 IK 生成的 `pregrasp_pulse/pick_pulse/lift_pulse`。profile 中的 `fixed_pick_sequence` 是备用配置，当前不会执行，除非策略改成 `aligned_fixed_pulse_sequence`。

真实发布序列如下：

| 阶段 | feedback status | 发布的 servo pulse | duration | 等待 |
| --- | --- | --- | --- | --- |
| 打开夹爪 | `opening_gripper` | `[(10, 150)]` | `0.6s` | `0.7s` |
| 只对齐底座 | `aligning_base` | `[(1, pregrasp[0]), (10, 150)]` | `0.8s` | `0.9s` |
| 到预抓取位 | `moving_pregrasp` | `[(1..5, pregrasp[0..4]), (10, 150)]` | `1.3s` | `1.4s` |
| 下探到抓取位 | `moving_pick` | `[(1..5, pick[0..4]), (10, 150)]` | `2.6s` | `3.2s` |
| 闭合夹爪 | `closing_gripper` | `[(10, 650)]` | `0.8s` | `1.4s` |
| 抬升 | `lifting` | `[(1..5, lift[0..4]), (10, 650)]` | `1.0s` | `1.0s` |
| 抓后复位 | `resetting_after_pick` | `[(1,500), (2,720), (3,100), (4,150), (5,500), (10,650)]` | `1.2s` | `1.4s` |

每次发布前 `_validate_servo_positions()` 检查 pulse 范围：

```text
servo 1..5: [0, 1000]
servo 10 gripper: [150, 760]
```

所以导师问“角度是多少”，要谨慎回答：

- 当前公开出来的是 servo pulse，不是角度。
- IK service 的输入包含 `position_m` 和 `pitch`，输出是 pulse。
- vendor action group `.d6a` 内部也是底层动作组文件，不是 Agent App 的业务代码。
- 不能把 pulse 硬说成角度，除非另有标定曲线。

导师问“加速度是多少”，准确回答：

- 代码没有 acceleration 字段。
- 当前控制风险靠 `duration_s`、`settle_s`、pulse limit、workspace bound、timeout、E-stop、resource lock 和 allowlist。
- 如果论文/答辩需要加速度曲线，下一步要在 bridge profile 和 servo controller 反馈中补 `velocity/acceleration` 采样或标定，不应该编造。

### 7.8 第八层：为什么运动成功不等于夹住

`execute_pick_color_block()` 返回的 `result_json` 里会写：

```json
{
  "motion_completed": true,
  "held": false,
  "held_verified": false,
  "held_claim_source": "post_pick_vision_verification_required",
  "pick_pulse": [...],
  "pregrasp_pulse": [...],
  "lift_pulse": [...],
  "pick_pitch": 76.0
}
```

也就是说，pick action success 只代表“运动序列执行完”。真正的成功由 `_post_pick_verify()` 决定。

`_post_pick_verify()` 做这些事：

1. `arm.get_state` 读取夹爪状态，拿 `last_gripper_command`。
2. `capture_photo` 拍 post-pick 图。
3. 把 pick result 加上 post-reset verification context。`gripper_closed_verified` 不是硬编码为 true，而是由 `arm.get_state` 返回的 `last_gripper_command` 是否包含 `close` 推出：

```json
{
  "verification_context": "post_reset_arm_home",
  "post_reset_arm_home": true,
  "gripper_closed_verified": "<derived from arm state>",
  "last_gripper_command": "<arm state last_gripper_command>"
}
```

4. 调 `perception.verify_held_color_block`。
5. 如果第一次通过，等待 `2.0s`。
6. 再拍一次图，再调一次 `verify_held_color_block`。
7. 两次都证明 held，才最终 `success=true`。

注意：pick 运动序列本身会发布 `servo10=650` 闭合夹爪；但当前成功判据不应该只依赖“夹爪命令发过”。真正的硬门槛是后面的视觉持有验证。

### 7.9 第九层：held verifier 的判定条件

代码位置是 `inspection_bridge_node.py::_verify_held_color_block()`。

它只在 gripper-held ROI 内找目标颜色：

```yaml
held_verify_roi_x_min_ratio: 0.20
held_verify_roi_x_max_ratio: 0.92
held_verify_roi_y_min_ratio: 0.72
held_verify_roi_y_max_ratio: 1.0
held_verify_min_area_px: 80
```

这意味着只看图像下方夹爪区域，不再全图找红色。

通过条件是逻辑与：

```text
verified =
  observation exists
  and confidence >= 0.001
  and not overlaps_pre_pick
  and radius_ratio_vs_pre_pick >= 1.15
  and depth_delta_m >= 0.09
  and center_y_ratio >= 0.82
  and bottom_y_ratio >= 0.90
```

各项解释：

| 条件 | 意义 |
| --- | --- |
| `observation exists` | 夹爪 ROI 中确实还能看到目标颜色 |
| `confidence >= 0.001` | 避免极小噪点 |
| `not overlaps_pre_pick` | 不能还在原桌面位置附近，排除“只是桌上红块没动” |
| `radius_ratio >= 1.15` | 抓起后更靠近相机，视觉半径应至少放大 15% |
| `depth_delta >= 0.09m` | 抓起后相机测得更近，深度至少减少 9cm |
| `center_y_ratio >= 0.82` | 候选中心在图像下方夹爪区域 |
| `bottom_y_ratio >= 0.90` | 候选底部接近夹爪口区域 |

失败原因也会精确返回，例如：

```text
held verification radius ratio 1.02 below 1.15
held verification depth delta 0.034m below 0.090m
verification candidate overlaps the pre-pick tabletop detection
```

最终 App 还会检查 verification payload：

```text
verified_held == true
target_color == task color
candidate exists
size_confirms_lift == true
overlaps_pre_pick_detection == false
position_confirms_gripper_roi == true
evidence_image_path exists
evidence_metadata_path exists
```

所以“红块消失了”不够，“运动执行了”也不够，必须有 post-pick 图像证据证明红块在夹爪 ROI 中。

### 7.10 第十层：放置或保持夹持

`place_target` 如果是：

```text
hold_position, held, lifted, keep_holding
```

`execute_place_color_block()` 直接返回：

```json
{
  "held": true,
  "released": false
}
```

也就是保持夹住，不打开夹爪。

如果是具体放置目标，默认 place sequence 是：

| step | positions | duration |
| --- | --- | --- |
| 1 | `[1=500,2=535,3=170,4=220,5=500,10=650]` | `1.5s` |
| 2 | `[1=500,2=160,3=400,4=350,5=500,10=650]` | `1.5s` |
| 3 | `[10=150]` | `1.0s` |
| 4 | `[1=500,2=667,3=21,4=188,5=500,10=150]` | `1.0s` |

其中 `servo10=150` 是打开夹爪，`servo10=650` 是闭合夹爪。

### 7.11 你可以在答辩时这样逐句讲

短版：

> 我们的 Agentic App 不直接控制 ROS2 或舵机，它把“夹红色物块”变成固定状态机。LLM 只输出 `target_color=red` 等计划字段。App 校验权限、要求人工确认，然后通过 Runtime 调用 perception 和 manipulation system skills。视觉 bridge 用 LAB 阈值分割红色区域，结合 depth 和 CameraInfo 把像素反投影成 `camera_position_m`。对中阶段用 `dx, dy` 误差调 servo1 和 servo4 的 pulse。抓取阶段把相机坐标通过手眼外参转换到机械臂坐标，加抓取偏移，调用 IK 得到 servo1..5 pulse，再按 open、pregrasp、pick、close、lift 的序列发布。最后不相信运动成功，必须用夹爪 ROI 的二次视觉验证证明红块真的被夹住。

导师追问版：

```text
1. 红色怎么识别？
   LAB threshold: red min [0,152,108], max [255,255,255]。
   resize 1/2、Gaussian blur、inRange、erode/dilate、contour、minEnclosingCircle。

2. 红块三维位置怎么来？
   depth ROI 均值 + 0.02m + 0.025m，超过 0.38m 拒绝；
   X=(u-cx)Z/fx, Y=(v-cy)Z/fy。

3. 为什么先对中？
   把红块中心对到图像 (0.52W, 0.78H)，容差 0.045；
   base_delta=clip(dx*-100,-8,8)，pitch_delta=clip(-dy*50,-8,8)。

4. 抓取点怎么来？
   T_world_hand @ T_hand_camera @ P_camera，再加 [0.012,0.027,0.094]m。

5. 机械臂怎么动？
   调 /kinematics/set_pose_target 求 pregrasp/pick/lift 三组 pulse；
   按 0.6s open、1.3s pregrasp、2.6s pick、0.8s close、1.0s lift 发布。

6. 怎么证明夹住？
   gripper ROI 内目标颜色存在、半径至少 1.15x、深度差至少 0.09m、
   不重叠 pre-pick 桌面位置、位置在夹爪口区域，并且 2 秒后复检仍成立。
```

### 7.12 参数字典：每个参数代表什么

这一节是答辩时最该背熟的部分。不要只说“有一些阈值”，要能说清楚每个参数的含义、单位、作用位置，以及调大会怎样。

#### LLM plan 参数

这些参数来自 Runtime LLM 的 JSON 输出，由 `main.py::_validate_plan()` 校验。它们不直接控制机器人，只决定 App 状态机是否允许继续。

| 参数 | 类型/示例 | 含义 | 用在哪里 | 调错/缺失会怎样 |
| --- | --- | --- | --- | --- |
| `schema_version` | `"1.0"` | plan schema 版本，防止不同版本字段混用。 | `_validate_plan()` | 非 `1.0` 返回 `COLOR_BLOCK_LLM_PLAN_INVALID`。 |
| `planner_mode` | `"llm"` | 标记这个 plan 来自系统 LLM，而不是规则兜底。 | `_validate_plan()`、结果 payload | 非 `llm` 被拒绝。 |
| `target_color` | `"red"` | 用户要抓取的目标颜色。 | 后续所有 perception/manipulation skill 的 `color` 参数。 | 必须在 `red/green/blue/yellow`，否则拒绝。 |
| `place_target` | `"hold_position"` | 抓取后放到哪里；`hold_position` 表示保持夹住。 | `_place_color_block()` -> `manipulation.place_color_block`。 | 空字符串被拒绝；非 hold target 会触发放置动作。 |
| `requires_manipulation` | `true` | 声明该任务会动机械臂/夹爪。 | `_validate_plan()`、`_validate_policy()` | 不是 `true` 说明 LLM 没识别出风险，拒绝。 |
| `needs_confirmation` | `true` | 是否需要人工确认。真实抓取必须为 true。 | `_confirm_manipulation()` | false 会被 policy 拒绝。 |
| `steps` | 固定 8 步 list | App 允许执行的确定性状态机顺序。 | `_validate_plan()` | 任何缺项、多项、乱序都拒绝。 |
| `risk_class` | `"controlled_manipulation"` | 风险等级，限定在受控 manipulation 范围内。 | policy step、结果记录 | 不在 allowlist 则拒绝。 |
| `user_summary` | 字符串 | 给人看的任务摘要。 | 结果、report | 空字符串拒绝。 |
| `target` | 默认 `"workspace"` | 感知目标区域。 | `perception.*` request 的 `target`。 | 为空时拒绝；默认 workspace。 |
| `evidence_label` | 默认 `red_block_grasp` | 证据文件标签前缀。 | capture/detect/verify evidence 文件命名。 | 为空时拒绝；影响可追溯性，不影响控制。 |
| `timeout_s` | 默认 `180` | App 级任务超时上限，用于裁剪子 skill timeout。 | 多个 `_call_skill()` 参数。 | 必须是 `1..600`；太大不会直接下发到底层，会被 skill/safety 再限制。 |

#### App 常量参数

这些在 `color_block_grasper_agent/main.py` 顶部定义，用来限制 App 行为。

| 参数 | 值 | 含义 | 为什么重要 |
| --- | --- | --- | --- |
| `PLAN_SCHEMA_VERSION` | `"1.0"` | 当前接受的 LLM plan schema。 | 防止 LLM 输出旧格式或未知格式。 |
| `HOLD_STABILITY_DELAY_S` | `2.0` 秒 | 第一次持有验证通过后等待多久再复检。 | 防止物块刚夹起但马上滑落。 |
| `ALLOWED_COLORS` | `red/green/blue/yellow` | App 层可接受颜色集合。 | LLM 不能发明颜色名。 |
| `CONFIRM_ANSWER` | `"CONFIRM"` | 人工确认必须输入的答案。 | 避免 yes/随意文本误触发真实抓取。 |
| `PLAN_STEPS` | 8 个固定步骤 | 唯一允许的执行顺序。 | 防止 LLM 跳过证据、跳过验证或直接抓。 |
| `RISK_CLASSES` | `controlled_manipulation`, `manipulation_real_hardware` | 可接受风险类型。 | 限定任务必须被识别为真实硬件风险。 |

#### Manifest 参数

这些在 `agentic_apps/color_block_grasper_agent/app.yaml`。

| 参数 | 含义 | 具体例子 |
| --- | --- | --- |
| `permissions` | App 被授予的权限集合。Runtime/SkillExecutor 根据它决定能否调用 skill。 | `manipulation.pick.color_block`、`perception.verify.color_block_held`。 |
| `required_capabilities` | App 期望 Runtime 提供的高层能力。用于 capability truth 和文档化依赖。 | `perception.detect_color_block`、`manipulation.pick_color_block`。 |
| `resources` | App 会占用的硬件/逻辑资源。 | `camera`、`arm`、`gripper`、`manipulation_backend`。 |
| `allowed_targets` | App 允许操作的目标区域。 | `workspace`。 |
| `safety_policy.allow_manipulation` | 是否允许 manipulation 类动作。 | 本 App 为 `true`。 |
| `safety_policy.require_human_confirmation_for` | 哪些能力必须人工确认。 | pick/place/gripper/arm move。 |
| `runtime_limits.max_concurrent_tasks` | 这个 App 同时允许几个任务。 | `1`，防止两个抓取任务并发抢机械臂。 |
| `runtime_limits.max_retries_per_skill` | skill 自动重试次数。 | `0`，真实硬件默认不盲目重试。 |
| `runtime_limits.max_memory_write_per_task` | 单任务最多写几次 memory。 | `20`。 |
| `runtime_limits.llm_planning_enabled` | 是否允许 LLM plan。 | `true`。 |
| `runtime_limits.llm_planning_provider` | 使用哪个 Runtime-owned LLM provider。 | `agenticos.runtime.llm_chat`。 |

#### ROS2 contract 参数

这些是 bridge service/action 的 request/result 字段。Agent App 不直接构造 ROS2 client，但 Runtime 最终会把 skill args 映射成这些字段。

| 参数 | 出现场景 | 含义 |
| --- | --- | --- |
| `color` | detect/center/pick/verify/place | 目标颜色，必须和 plan 的 `target_color` 一致。 |
| `target` | detect/center/capture/verify/pick | 感知或操作区域，如 `workspace`。 |
| `place_target` | place action | 放置目标；`hold_position` 表示不释放。 |
| `evidence_label` | detect/center/verify | 证据文件标签，用于生成 debug image/metadata 文件名。 |
| `request_id` | 所有 bridge contract | 请求唯一 ID，用于日志、证据和审计关联。 |
| `timeout_s` | 所有 bridge contract | 单次 service/action 最长等待时间；还会被 skill/safety 限制。 |
| `detection_json` | pick/verify | 上游检测结果 JSON，包含颜色、像素中心、深度和相机坐标。 |
| `evidence_json` | pick input / perception output | 图像证据 metadata，例如 topic、frame、文件路径。 |
| `pick_result_json` | verify/place | 抓取 action 的输出，包含 pulse、pick pose、运动完成状态。 |
| `alignment_json` | center response | 对中结果，包含最终 pulse、迭代记录、是否 centered。 |
| `verification_json` | verify response | 持有验证结果，包含 ROI、candidate、深度差、半径比例等。 |
| `result_json` | pick/place result | manipulation action 的结构化结果。 |
| `feedback.status` | pick/place feedback | 当前动作阶段，如 `moving_pick`、`closing_gripper`。 |
| `feedback.progress` | pick/place feedback | 进度，0 到 1 的浮点数。 |
| `feedback_json` | pick/place feedback | 阶段细节，如当前 pulse、duration。 |

#### Camera profile 参数

这些在 `agentic_runtime_src/configs/robot_profiles/rosorin_arm_camera.yaml` 的 `camera` 区域。

| 参数 | 值/单位 | 含义 | 影响 |
| --- | --- | --- | --- |
| `camera.mode` | `rgb_depth_optional` | 相机模式描述。当前检测实际需要 RGB，颜色抓取还需要 depth 和 CameraInfo。 | 文档/配置语义。 |
| `primary_rgb_topic` | `/depth_cam/rgb0/image_raw` | 优先 RGB 图像 topic。 | 没有 fresh frame 会 fallback 或失败。 |
| `fallback_rgb_topics` | `/camera/color/image_raw` | 主 RGB 不可用时的备选。 | 提高兼容性。 |
| `primary_depth_topic` | 未显式配置 | 优先 depth topic。 | 未配置时用 `depth_topics`。 |
| `depth_topics` | `/depth_cam/depth0/image_raw`, `/camera/depth/image_raw` | depth 图像 topic。 | 缺失时检测返回 `DEPTH_UNAVAILABLE`。 |
| `camera_info_topics` | 多个 CameraInfo topic | 相机内参来源。 | 缺失时不能做像素到 3D 反投影。 |
| `point_cloud_topics` | point cloud topic list | 当前抓红块路径没有直接使用。 | 可作为未来 3D perception 扩展。 |
| `frame_freshness_s` | `5.0s` | 图像/depth/CameraInfo 多久以内算新鲜。 | 太小易失败，太大可能用旧帧。 |
| `observe_timeout_s` | `5s` | 默认等待图像时间。 | 影响 observe/capture 默认等待。 |

#### Evidence 参数

| 参数 | 值 | 含义 |
| --- | --- | --- |
| `evidence.directory` | `/opt/agentic/var/evidence` | Runtime/bridge 写真实图片、检测 metadata、验证 metadata 的根目录。 |
| `image_path` | 运行时生成 | 保存的原始或 debug 图片路径。 |
| `metadata_path` | 运行时生成 | 保存的 JSON metadata 路径。 |
| `debug_image_path` | 运行时生成 | 画了检测圆、ROI、状态文字的调试图。 |

#### Arm profile 参数

| 参数 | 值/单位 | 含义 | 影响 |
| --- | --- | --- | --- |
| `arm.backend_type` | `servo_action_group` | 机械臂后端类型。 | 决定 `arm.move_named` 使用 vendor action group controller。 |
| `action_command_topic` | `/servo_controller` | 非 direct backend 时的动作命令 topic；当前 direct action group 路径不主要用它。 | 后端兼容。 |
| `action_status_service` | `""` | 非 direct backend 状态服务。 | 当前为空。 |
| `action_group_path` | `/home/ubuntu/software/arm_pc/ActionGroups` | vendor `.d6a` 动作组文件目录。 | `arm_home` 等 named action 查这里。 |
| `servo_command_topic` | `/servo_controller` | servo pulse 发布 topic。 | 没有 subscriber 则 arm/gripper backend 不可用。 |
| `kinematics_pose_service` | `/kinematics/set_pose_target` | IK 服务，把目标位置和 pitch 转成 pulse。 | 不可用则不能抓。 |
| `max_duration_s` | `8s` | named arm action 最长时间。 | 超过返回 `ARM_TIMEOUT_LIMIT_EXCEEDED`。 |
| `allowed_named_actions.arm_home.backend_action` | `init` | `arm_home` 对应 vendor 动作组文件 `init.d6a`。 | 让机械臂回初始安全姿态。 |
| `allowed_named_actions.camera_center.backend_action` | `horizontal` | 相机居中动作组。 | 用于检查/拍照类姿态。 |
| `allowed_named_actions.camera_yaw_left_15.backend_action` | `detect_left` | 左视角检查动作组。 | 多角度拍照/检查用。 |
| `allowed_named_actions.camera_yaw_right_15.backend_action` | `detect_right` | 右视角检查动作组。 | 多角度拍照/检查用。 |
| `allowed_named_actions.camera_pitch_up_15.backend_action` | `camera_up` | 上仰视角动作组。 | 多角度拍照/检查用。 |
| `allowed_named_actions.*.duration_s` | `5s` | vendor action group 期望执行时长。 | 超过 max duration 会被拒绝。 |
| `workspace_bounds_m.x` | `[0.12, 0.32] m` | 抓取点 x 范围。 | 越界拒绝抓取。 |
| `workspace_bounds_m.y` | `[-0.18, 0.18] m` | 抓取点 y 范围。 | 越界拒绝抓取。 |
| `workspace_bounds_m.z` | `[0.03, 0.36] m` | 抓取点 z 范围。 | 越界拒绝抓取。 |
| `joint_pulse_limits.joint1..5` | `[0,1000] pulse` | 每个机械臂舵机 pulse 安全范围。 | `_validate_servo_positions()` 越界抛错。 |
| `stop_backend.type` | `action_group_controller.stop_action_group` | active action 停止方式。 | cancel/timeout/error 时调用。 |

#### Gripper 参数

| 参数 | 值/单位 | 含义 | 影响 |
| --- | --- | --- | --- |
| `gripper.backend_type` | `servo_controller` | 夹爪后端是 servo controller。 | 通过 pulse 控制开合。 |
| `servo_command_topic` | `/servo_controller` | 夹爪命令 topic。 | 无 subscriber 则 `BACKEND_UNAVAILABLE`。 |
| `servo_id` | `10` | 夹爪对应 servo ID。 | 抓取/放置序列用 `servo10`。 |
| `position_unit` | `pulse` | 位置单位。 | 不是角度，是 pulse。 |
| `duration_s` | `0.6s` | 单独 `gripper.set` 默认动作时间。 | 控制开合动作持续时间。 |
| `limits.min_pulse` | `150` | 夹爪最小 pulse。 | 低于拒绝。 |
| `limits.max_pulse` | `760` | 夹爪最大 pulse。 | 高于拒绝。 |
| `limits.open_pulse` | `200` | profile 中通用 open pulse。 | `gripper.set(open)` 默认用它。 |
| `limits.close_low_force_pulse` | `650` | 低力闭合 pulse。 | `gripper.set(close, low)` 用它。 |
| `color_block.gripper_open` | `150` | 抓取序列专用打开 pulse。 | pick motion 里开夹爪用 150。 |
| `color_block.gripper_close` | `650` | 抓取序列专用闭合 pulse。 | pick motion 里闭夹爪用 650。 |
| `allowed_commands.open_gripper.command` | `open` | allowlist 中的打开命令语义。 | 其他命令拒绝。 |
| `allowed_commands.open_gripper.force` | `low` | 打开命令的力级别。 | 当前只允许 low。 |
| `allowed_commands.close_gripper_low_force.command` | `close` | allowlist 中的闭合命令语义。 | 其他闭合方式拒绝。 |
| `allowed_commands.close_gripper_low_force.force` | `low` | 低力闭合。 | 防止高力夹持。 |

#### 颜色分割参数

| 参数 | 值/单位 | 含义 | 调大会怎样 |
| --- | --- | --- | --- |
| `lab_ranges.red.min` | `[0,152,108]` | 红色在 LAB 空间的下界。 | 范围变窄，误检少但漏检多。 |
| `lab_ranges.red.max` | `[255,255,255]` | 红色在 LAB 空间的上界。 | 范围变宽，漏检少但误检多。 |
| `lab_ranges.blue.min/max` | `[50,116,100]` 到 `[120,130,116]` | 蓝色 LAB 阈值。 | 同上。 |
| `lab_ranges.green.min/max` | `[90,90,126]` 到 `[230,120,150]` | 绿色 LAB 阈值。 | 同上。 |
| `detect_roi_x_max_ratio` | `0.78` | 检测区域右边界比例。 | 变大可看更右侧，误检区域也更大。 |
| `detect_roi_y_min_ratio` | `0.08` | 检测区域上边界比例。 | 变小可看更上方，可能误检背景。 |
| `min_area_px` | `50 px` | detect 阶段最小轮廓面积。 | 变大抗噪更强但小块可能漏检。 |
| `held_verify_min_area_px` | `80 px` | held 验证阶段最小面积。 | 比 detect 更严格，避免小噪点当成夹住。 |

#### 深度与三维定位参数

| 参数 | 值/单位 | 含义 | 影响 |
| --- | --- | --- | --- |
| `roi_radius_px` | `5 px` | depth ROI 最小半径。 | 太小易受噪点影响，太大可能混入背景。 |
| `depth_roi_radius_scale` | `1.0` | depth ROI 半径相对 color radius 的比例。 | 大于 1 会取更大深度区域。 |
| `object_radius_compensation_m` | `0.02m` | 对物块半径/表面几何的深度补偿。 | 增大会认为物块更远。 |
| `depth_error_compensation_m` | `0.025m` | 对 depth 误差的经验补偿。 | 增大会让抓取点更保守偏远。 |
| `max_distance_m` | `0.38m` | 检测允许的最大深度。 | 超过直接 `DEPTH_INVALID`。 |
| `depth_valid_count` | 运行时统计 | depth ROI 中有效深度点数量。 | 太少说明深度证据弱。 |
| `depth_roi_bounds` | 运行时生成 | `[y0, y1, x0, x1]` depth ROI 像素范围。 | 用于审计深度来自哪里。 |
| `camera_position_m` | 运行时生成 | 目标在相机坐标系下的 `[X,Y,Z]`。 | 抓取规划的核心输入。 |

#### 视觉对中参数

| 参数 | 值/单位 | 含义 | 影响 |
| --- | --- | --- | --- |
| `center_timeout_s` | `8.0s` | 对中总超时。 | 太短可能未对中，太长占用硬件。 |
| `center_target_x_ratio` | `0.52` | 希望目标中心在图像宽度 52% 处。 | 改变水平抓取参考点。 |
| `center_target_y_ratio` | `0.78` | 希望目标中心在图像高度 78% 处。 | 改变垂直抓取参考点。 |
| `center_tolerance_ratio` | `0.045` | 对中误差容忍比例。 | 变小更精确但更难收敛。 |
| `center_base_start_pulse` | `500` | 对中前 base servo 初始 pulse。 | 初始视角。 |
| `center_pitch_start_pulse` | `188` | 对中前 pitch servo 初始 pulse。 | 初始俯仰视角。 |
| `center_base_pulse_limits` | `[440,560]` | 对中时 base servo 允许范围。 | 防止相机/机械臂大幅摆动。 |
| `center_pitch_pulse_limits` | `[120,260]` | 对中时 pitch servo 允许范围。 | 防止俯仰越界。 |
| `center_base_gain` | `-100.0` | 水平误差到 base pulse 的比例系数。 | 绝对值越大，一次修正越猛。符号决定方向。 |
| `center_pitch_gain` | `50.0` | 垂直误差到 pitch pulse 的比例系数。 | 越大垂直修正越快，也越容易震荡。 |
| `center_max_servo_step` | `8 pulse` | 单轮最大 pulse 改变量。 | 限制视觉伺服速度。 |
| `center_max_iterations` | `18` | 最大对中迭代次数。 | 超过还没 centered 就失败。 |
| `center_servo_duration_s` | `0.08s` | 每次 servo 小步动作时长。 | 越大动作更慢。 |
| `center_settle_s` | `0.20s` | 每次动作后等待画面稳定时间。 | 太短可能读到运动模糊帧。 |

#### 抓取坐标与 IK 参数

| 参数 | 值/单位 | 含义 | 影响 |
| --- | --- | --- | --- |
| `hand2cam_tx_m` | `-0.101m` | camera frame 相对 hand frame 的 x 平移。 | 手眼标定参数，错了抓取点会系统性偏移。 |
| `hand2cam_ty_m` | `0.0m` | camera 相对 hand 的 y 平移。 | 同上。 |
| `hand2cam_tz_m` | `0.037m` | camera 相对 hand 的 z 平移。 | 同上。 |
| `pick_x_offset_m` | `0.012m` | 抓取点 x 方向经验补偿。 | 调大会往 x 正方向抓。 |
| `pick_y_offset_m` | `0.027m` | 抓取点 y 方向经验补偿。 | 调大会往 y 正方向抓。 |
| `pick_z_offset_m` | `0.094m` | 抓取点 z 方向经验补偿。 | 调大抓取点更高，可能夹不到；调小可能撞桌。 |
| `pregrasp_height_m` | `0.04m` | 预抓取点比抓取点高多少。 | 越大下探距离越长。 |
| `lift_height_m` | `0.08m` | 抓住后抬升高度。 | 太小验证不明显，太大可能越界。 |
| `near_z_threshold_m` | `0.20m` | 近/远抓取 pitch 切换阈值。 | 小于它用 near pitch。 |
| `pick_pitch_near` | `76.0 deg` | 近距离抓取末端 pitch。 | 影响 IK 姿态。 |
| `pick_pitch_far` | `30.0 deg` | 远距离抓取末端 pitch。 | 影响 IK 姿态。 |
| `pitch_range_min` | `-180.0 deg` | IK 搜索 pitch 下限。 | 搜索范围边界。 |
| `pitch_range_max` | `180.0 deg` | IK 搜索 pitch 上限。 | 搜索范围边界。 |
| `pitch_resolution` | `1.0 deg` | IK pitch 搜索分辨率。 | 越小搜索更细但可能更慢。 |
| `pick_position_m` | 运行时生成 | 加完 offset 后的真实抓取点。 | IK 核心输入。 |
| `pregrasp_position_m` | 运行时生成 | 抓取点上方 `0.04m`。 | 先到安全上方。 |
| `lift_position_m` | 运行时生成 | 抓取点上方 `0.08m`。 | 抓住后抬起。 |
| `pick_pulse` | 运行时 IK 输出 | 抓取点 servo1..5 pulse。 | 真正发给 servo 的位置。 |
| `pregrasp_pulse` | 运行时 IK 输出 | 预抓取点 servo1..5 pulse。 | 接近目标前的位置。 |
| `lift_pulse` | 运行时 IK 输出 | 抬升点 servo1..5 pulse。 | 抓住后的抬升位置。 |

#### 抓取运动时序参数

| 参数/阶段 | 值 | 含义 |
| --- | --- | --- |
| `pick_execution_strategy` | `ik_color_block_pick` | 使用 IK 生成 pulse，而不是固定动作组。 |
| `gripper_open` | `150 pulse` | pick 序列中打开夹爪的 pulse。 |
| `gripper_close` | `650 pulse` | pick 序列中闭合夹爪的 pulse。 |
| `opening_gripper.duration` | `0.6s` | 打开夹爪动作时长。 |
| `opening_gripper.settle` | `0.7s` | 打开后等待稳定。 |
| `aligning_base.duration` | `0.8s` | 只调整 base 到 pregrasp base 的时长。 |
| `aligning_base.settle` | `0.9s` | base 调整后等待稳定。 |
| `moving_pregrasp.duration` | `1.3s` | 移动到预抓取姿态的时长。 |
| `moving_pregrasp.settle` | `1.4s` | 预抓取后等待稳定。 |
| `pick_move_duration_s` | `2.6s` | 下探到抓取位的动作时长。 |
| `pick_settle_s` | `3.2s` | 到达抓取位后等待稳定时间。 |
| `closing_gripper.duration` | `0.8s` | 闭合夹爪动作时长。 |
| `closing_gripper.settle` | `1.4s` | 闭合后等待夹持稳定。 |
| `lifting.duration` | `1.0s` | 抬升动作时长。 |
| `lifting.settle` | `1.0s` | 抬升后等待稳定。 |
| `resetting_after_pick.duration` | `1.2s` | 抓后回验证姿态动作时长。 |
| `resetting_after_pick.settle` | `1.4s` | 复位后等待视觉稳定。 |

#### Held verification 参数

| 参数 | 值/单位 | 含义 | 调大会怎样 |
| --- | --- | --- | --- |
| `held_verify_roi_x_min_ratio` | `0.20` | 夹爪 ROI 左边界。 | 变大看更靠右，可能漏掉夹爪左侧物体。 |
| `held_verify_roi_x_max_ratio` | `0.92` | 夹爪 ROI 右边界。 | 变小排除右侧背景，但可能漏检。 |
| `held_verify_roi_y_min_ratio` | `0.72` | 夹爪 ROI 上边界。 | 变大只看更下方，更严格。 |
| `held_verify_roi_y_max_ratio` | `1.0` | 夹爪 ROI 下边界。 | 通常是图像底部。 |
| `held_verify_min_area_px` | `80 px` | 持有候选最小面积。 | 变大更抗噪，但小块可能失败。 |
| `held_verify_min_confidence` | `0.001` | 最低颜色面积置信度。 | 变大更严格。 |
| `held_verify_pre_pick_exclusion_radius_px` | `45 px` | 与 pre-pick 桌面位置的排斥半径。 | 变大更严格，防止桌上原位置误判。 |
| `held_verify_min_radius_ratio_vs_pre_pick` | `1.15` | 抓后半径 / 抓前半径最小比例。 | 变大要求更明显靠近相机。 |
| `held_verify_min_depth_delta_m` | `0.09m` | 抓前深度 - 抓后深度的最小差。 | 变大要求抬得更明显。 |
| `held_verify_min_center_y_ratio` | `0.82` | 候选中心必须足够靠下。 | 变大更靠近夹爪口，漏检风险上升。 |
| `held_verify_min_bottom_y_ratio` | `0.90` | 候选底部必须足够靠下。 | 防止上方背景红色误判。 |
| `verified_held` | runtime bool | 持有验证最终结果。 | App 成功必须为 true。 |
| `radius_ratio_vs_pre_pick` | runtime float | 抓后半径 / 抓前半径。 | 证明物块更近。 |
| `depth_delta_m` | runtime m | 抓前深度 - 抓后深度。 | 证明物块离相机更近。 |
| `overlaps_pre_pick_detection` | runtime bool | 抓后候选是否还在原桌面检测附近。 | 必须为 false。 |
| `position_confirms_gripper_roi` | runtime bool | 候选是否在夹爪口位置。 | 必须为 true。 |

#### Safety 参数

这些在 `agentic_runtime_src/configs/safety.yaml`，由 safety guard 或 skill constraints 使用。

| 参数 | 值/单位 | 含义 |
| --- | --- | --- |
| `require_estop_released` | `true` | 需要急停释放才能执行危险动作。 |
| `max_linear_speed_mps` | `0.5 m/s` | 底盘导航速度上限。本抓取 App 不移动底盘。 |
| `max_angular_speed_radps` | `0.8 rad/s` | 底盘角速度上限。本抓取 App 不移动底盘。 |
| `max_navigation_duration_s` | `120s` | 导航最长时间。本抓取 App 不用。 |
| `max_task_duration_s` | `300s` | 总任务建议上限。 |
| `forbidden_zones` | stairs/elevator/lab_restricted_zone | 禁区列表。 |
| `camera.max_capture_duration_s` | `20s` | 拍照最长时间。 |
| `manipulation.max_arm_duration_s` | `8s` | named arm action 最长时长。 |
| `manipulation.allowed_named_actions` | `arm_home` 等 | 只允许这些 named action。 |
| `manipulation.allowed_gripper_commands` | `open`, `close` | 只允许开/关夹爪。 |
| `manipulation.allowed_gripper_forces` | `low` | 只允许低力。 |
| `manipulation.workspace_bounds_m` | x/y/z 范围 | safety 层工作空间边界。 |
| `manipulation.gripper_pulse_limits` | `[350,760]` in safety config | safety 层夹爪 pulse 限制；bridge profile 还有自己的 `[150,760]`。 |

注意最后一项：profile 中 `gripper_open=150`，但 safety config 的 `gripper_pulse_limits.min_pulse=350` 主要约束 `gripper.set` 类 safety check；pick motion 走 manipulation bridge 的内部序列和 `_validate_servo_positions()`。答辩时不要把两个层的限制混成一个。

### 7.13 真实夹取动作的底层控制链路：从 action 到串口包

如果导师继续追问“真实夹取到底怎么控制”，不能停在“调用 manipulation skill”。要从上到下讲清楚这条链：

```text
Agent App
  -> Runtime skill: manipulation.pick_color_block
  -> ROS2 action: /agentic/manipulation/pick_color_block
  -> ManipulationBridgeNode._execute_pick_motion()
  -> publish servo_controller_msgs/ServosPosition to /servo_controller
  -> servo_controller.ControllerManager.servo_controller_callback()
  -> ServoManager.set_position()
  -> publish ros_robot_controller_msgs/ServosPosition to /ros_robot_controller/bus_servo/set_position
  -> RosRobotController.set_bus_servo_position()
  -> Board.bus_servo_set_position()
  -> serial packet on /dev/rrc, baudrate 1000000
  -> STM32 / robot controller board
  -> bus servo firmware moves each servo to target pulse within duration
```

这里的第一性原理是：

> Agent App 不实时控电机；Agentic Runtime 管授权、锁、审计和能力边界；ROS2 bridge 把“夹红块”变成一组受限 servo pulse；vendor 驱动把 pulse 和 duration 编码成总线舵机串口命令；真正的插补、保持、PID 或电流控制在控制板/舵机固件里。

#### 7.13.1 pick action 如何变成三组 IK pulse

`_plan_color_block_pick()` 不是直接写 servo，而是先求出三个目标点：

```text
pick_position     = [x, y, z]
pregrasp_position = [x, y, z + pregrasp_height_m]
lift_position     = [x, y, z + lift_height_m]
```

当前参数是：

```text
pregrasp_height_m = 0.04
lift_height_m     = 0.08
```

然后分别调用 `/kinematics/set_pose_target`。这个 service 的真实字段是：

```text
request:
  float64[] position       # [x, y, z], unit=m
  float64   pitch          # end-effector pitch, unit=deg
  float64[] pitch_range    # search range, unit=deg
  float64   resolution     # pitch search step, unit=deg

response:
  bool      success
  uint16[]  pulse          # servo1..5 target pulse
  uint16[]  current_pulse  # servo1..5 current pulse
  float64[] rpy            # selected end-effector rpy
  float64   min_variation  # selected solution's total pulse movement
```

IK 节点内部逻辑是：

```text
all_solutions = get_ik(position, pitch, pitch_range, resolution)
for each solution:
    pulse_solutions = angle2pulse(solution)
    d = pulse_solution - current_servo_positions
    min_sum = sum(abs(d))
choose solution with smallest min_sum
clip each pulse to [0, 1000]
```

所以“为什么是这组关节目标”可以这样解释：IK 先找所有几何可达解，再选相对当前姿态总 pulse 变化最小的解，目的是减少不必要的大幅摆动。

#### 7.13.2 bridge 发布的第一层舵机消息

`_execute_pick_motion()` 每个阶段调用 `_publish_servos(duration_s, positions)`。它构造的是 `servo_controller_msgs/ServosPosition`：

```text
float64 duration
string position_unit
servo_controller_msgs/ServoPosition[] position

ServoPosition:
  uint16  id
  float32 position
```

当前 bridge 发的是：

```text
position_unit = "pulse"
duration      = stage duration in seconds
position      = [{id: servo_id, position: target_pulse}, ...]
```

这一层每个字段的含义：

| 字段 | 例子 | 含义 |
| --- | --- | --- |
| `duration` | `0.8` | 希望这批 servo 在 `0.8s` 内到达目标，不只是程序 sleep。 |
| `position_unit` | `"pulse"` | 后续 controller 不再做 rad/deg 转换，按 pulse 解释。 |
| `id` | `1` 到 `5`，`10` | servo ID。`1..5` 是机械臂关节，`10` 是夹爪。 |
| `position` | `650.0` | 目标 pulse。bridge 用 float 填，但后续会转整数。 |

当前 pick 的真实阶段命令是：

```text
opening_gripper:
  duration=0.6
  positions=[(10, 150)]

aligning_base:
  duration=0.8
  positions=[(1, pregrasp[0]), (10, 150)]

moving_pregrasp:
  duration=1.3
  positions=[(1, pregrasp[0]), (2, pregrasp[1]), (3, pregrasp[2]),
             (4, pregrasp[3]), (5, pregrasp[4]), (10, 150)]

moving_pick:
  duration=2.6
  positions=[(1, pick[0]), (2, pick[1]), (3, pick[2]),
             (4, pick[3]), (5, pick[4]), (10, 150)]

closing_gripper:
  duration=0.8
  positions=[(10, 650)]

lifting:
  duration=1.0
  positions=[(1, lift[0]), (2, lift[1]), (3, lift[2]),
             (4, lift[3]), (5, lift[4]), (10, 650)]

resetting_after_pick:
  duration=1.2
  positions=[(1, 500), (2, 720), (3, 100),
             (4, 150), (5, 500), (10, 650)]
```

每次 publish 前，bridge 自己先做范围检查：

```text
servo 1..5: 0 <= pulse <= 1000
servo 10 : 150 <= pulse <= 760
```

这一步失败就抛异常，action 返回 `COLOR_BLOCK_PICK_FAILED`，不会把越界 pulse 发到底层。

#### 7.13.3 `/servo_controller` 如何处理 pulse

`controller_manager` 订阅的是 `servo_controller` topic。收到 message 后：

```text
if position_unit == "pulse":
    keep only connected servo IDs
    ServoManager.set_position(msg.duration, data.position)
elif position_unit == "rad":
    convert rad -> pulse
elif position_unit == "deg":
    convert deg -> rad -> pulse
```

当前 bridge 总是发 `"pulse"`，所以不会走角度转换。

`ServoManager.set_position()` 做第二层约束和类型收敛：

```text
duration = clamp(duration, 0.02, 30.0)
for each servo:
    position = int(i.position)
    position = clamp(position, 0, 1000)
publish ros_robot_controller_msgs/ServosPosition
```

第二层消息是 `ros_robot_controller_msgs/ServosPosition`：

```text
float64 duration
ros_robot_controller_msgs/ServoPosition[] position

ServoPosition:
  uint16 id
  uint16 position
```

注意这里已经没有 `position_unit` 了，因为进入 `ros_robot_controller` 时一定是底层 pulse。

#### 7.13.4 pulse 和角度的关系

driver 里有一个通用换算常量：

```text
RADIANS_PER_ENCODER_TICK = 240 / 360 * 2*pi / 1000
                         ≈ 0.00418879 rad/pulse
                         ≈ 0.24 deg/pulse
```

关节配置里当前是：

```yaml
joint1..joint5:
  init: 500
  min: 1000
  max: 0
r_joint:
  id: 10
  init: 700
  min: 1000
  max: 0
```

因为 `min > max`，`JointPositionController` 会标记为 `flipped=True`。如果某个 joint 用 rad/deg 输入，换算公式是：

```text
pulse = init - angle_rad / 0.00418879
angle_rad = (init - pulse) * 0.00418879
```

但当前 pick path 直接发 pulse，所以最严谨的说法是：

> 在本夹取路径里，桥接层直接控制 servo target pulse；`0.24 deg/pulse` 是 driver 对 joint state 或 rad/deg 输入的近似换算，不等价于夹爪开口宽度，也不应该把所有 pulse 直接当作末端角度。

#### 7.13.5 `duration`、速度和加速度怎么讲

这套 pick command 没有 acceleration 字段，也没有 velocity 字段。底层命令只有：

```text
target_pulse
duration_s
```

可以严谨计算的是平均 pulse 速度：

```text
avg_pulse_speed = abs(target_pulse - previous_pulse) / duration_s
```

如果只做 servo shaft 的近似角速度估算，可以乘 `0.24 deg/pulse`：

```text
avg_angle_speed_deg_s ≈ avg_pulse_speed * 0.24
```

例子：夹爪从 open `150` 到 close `650`，duration `0.8s`：

```text
delta_pulse = 650 - 150 = 500 pulse
avg_pulse_speed = 500 / 0.8 = 625 pulse/s
avg_servo_shaft_speed ≈ 625 * 0.24 = 150 deg/s
```

但不能说“加速度是多少”，因为当前代码没有向底层下发加速度 profile，也没有从舵机反馈重建速度/加速度曲线。更严谨的答法是：

> AgenticOS 当前把运动约束在目标 pulse、duration、workspace bound、pulse limit、timeout、cancel、E-stop、resource lock 和 post-pick verification 上；具体插补曲线和加速度由控制板/舵机固件实现。论文如果要给出真实加速度，需要额外采样 servo position over time 或读取固件 profile，而不是从 App 代码里编造。

#### 7.13.6 `ros_robot_controller` 如何变成控制板串口包

`RosRobotController` 订阅：

```text
/ros_robot_controller/bus_servo/set_position
```

callback 做的事很薄：

```text
data = [[servo.id, servo.position], ...]
board.bus_servo_set_position(msg.duration, data)
```

`Board.bus_servo_set_position(duration, positions)` 把秒转换成毫秒：

```text
duration_ms = int(duration * 1000)
```

然后构造 bus servo data：

```text
data = [
  0x01,                         # bus servo subcommand: set position
  duration_ms & 0xFF,           # duration low byte
  (duration_ms >> 8) & 0xFF,    # duration high byte
  len(positions),               # number of servos
  servo_id_1, pos_1_low, pos_1_high,
  servo_id_2, pos_2_low, pos_2_high,
  ...
]
```

每个 servo 用：

```text
struct.pack("<BH", servo_id, position)
```

也就是小端序：

```text
B = uint8 servo_id
H = uint16 pulse
```

最后 `buf_write(PacketFunction.PACKET_FUNC_BUS_SERVO, data)` 包一层串口协议：

```text
buf = [
  0xAA, 0x55,          # header
  0x05,                # function: PACKET_FUNC_BUS_SERVO
  len(data),           # data length
  ...data,
  checksum_crc8(buf[2:])
]
serial.write(buf)
```

闭合夹爪的真实例子：

```text
bridge command:
  duration = 0.8s
  positions = [(10, 650)]

duration_ms = 800 = 0x0320
position    = 650 = 0x028A

bus servo data:
  [0x01, 0x20, 0x03, 0x01, 0x0A, 0x8A, 0x02]

full serial bytes:
  [0xAA, 0x55, 0x05, 0x07,
   0x01, 0x20, 0x03, 0x01, 0x0A, 0x8A, 0x02,
   0x82]
```

解释每个 byte：

| byte | 值 | 含义 |
| --- | --- | --- |
| 0 | `0xAA` | packet header 1 |
| 1 | `0x55` | packet header 2 |
| 2 | `0x05` | function = bus servo |
| 3 | `0x07` | data 长度 7 bytes |
| 4 | `0x01` | bus servo set position 子命令 |
| 5 | `0x20` | duration 低字节 |
| 6 | `0x03` | duration 高字节，`0x0320 = 800ms` |
| 7 | `0x01` | 本包控制 1 个 servo |
| 8 | `0x0A` | servo id 10，也就是夹爪 |
| 9 | `0x8A` | pulse 低字节 |
| 10 | `0x02` | pulse 高字节，`0x028A = 650` |
| 11 | `0x82` | CRC8 校验 |

这就是“夹爪闭合”真正到底层的形式：不是一句自然语言，不是一个 LLM token，而是一帧带 CRC 的总线舵机串口包。

#### 7.13.7 named action group 和当前 pick path 的区别

`arm.move_named("arm_home")` 这类 named action 会走 `ActionGroupController.run_action(action_name)`，它读取 `.d6a` SQLite 动作组：

```text
select * from ActionGroup
for each row:
    duration = act[1] / 1000.0
    servo positions = act[2:]
    if column maps to servo 6, send id 10
    publish ServosPosition(position_unit="pulse") to /servo_controller
```

所以 named action group 本质也是 pulse table。

但当前 color block pick 不是读取固定 `.d6a` 表，它是：

```text
vision 3D point
  -> camera-to-arm transform
  -> IK
  -> dynamic pregrasp/pick/lift pulse
  -> direct /servo_controller publish
```

只有 profile 显式改成 `pick_execution_strategy=aligned_fixed_pulse_sequence` 时，才会走固定 `fixed_pick_sequence`。

#### 7.13.8 cancel、stop 和反馈闭环的真实边界

当前 pick 序列有 cancel 检查，但不是实时 1kHz 伺服闭环：

```text
_sleep_or_cancel():
  every <= 0.05s:
      if goal_handle.is_cancel_requested:
          raise RuntimeError("motion cancelled")
```

异常后 action abort，并调用 `_stop_active_arm("pick_color_block_error")`。direct action group backend 下，stop 会调用 `ActionGroupController.stop_action_group()`。

但要讲清楚边界：

- bridge 不在每 20ms 读取 servo 反馈并重新规划。
- `/controller_manager/joint_states` 会周期性发布 joint state，但当前 pick bridge 不用它做实时闭环控制。
- 每个舵机命令发出后，bridge 靠 `settle_s` 等待物理动作完成。
- 对已经发出的单帧 `target_pulse + duration` 命令，当前 pick path 没有额外发布 `bus_servo_stop` 去硬中断总线舵机；cancel 的主要效果是尽快退出等待、停止进入后续阶段、让 action abort，并触发上层错误处理。
- 是否真的夹住，不由“命令发过”证明，而由 post-pick 视觉验证证明。

这符合 AgenticOS 的边界：LLM / Agent logic 不做 realtime closed-loop control；所有危险动作经过 Runtime permission、resource lock、safety guard 和 audit，然后由 ROS2 bridge 作为硬件适配层向底层控制器下发受限命令。

## 8. 推荐学习路径

1. 先读 `agentic_apps/app_template`，理解最小目录和 Runtime smoke。
2. 再读 `agentic_apps/hello_world_agent`，理解 LLM JSON plan、context、memory、storage、tool、skill 和 report。
3. 然后读 `agentic_runtime_src/docs/app_developer_interface.md`，查完整 SDK 行为、错误码和运行命令。
4. 最后读 `agentic_apps/color_block_grasper_agent` 或 `robot_photographer_agent`，学习真实机器人能力如何做确认、验证、证据归档和失败收敛。

核心记忆句：

> Agentic App 写的是“可授权、可暂停、可审计的任务编排”；ROS2 bridge 写的是“受 Runtime 管理的硬件/中间件适配”；实时控制永远不属于 LLM 或 Agent App。
