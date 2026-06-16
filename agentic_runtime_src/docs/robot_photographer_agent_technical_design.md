# Robot Photographer Agent 技术设计与实现计划

本文档是 `robot_photographer_agent` 的 source of truth。

目标是把 Robot Photographer 做成一个 **AIOS/Cerebrum-compatible Agent App package**，同时保留 **AgenticOS-safe 真实机器人执行边界**。它不是 ROS2 node，不是普通聊天机器人，也不是 SDK 测试例子；它是一个可加载、可运行、可发布的 agent package，通过 AgenticOS Runtime/Kernel 的受控能力调用真实相机和机械臂。

## 1. 产品定位

推荐 app id：

```text
robot_photographer_agent
```

英文名：

```text
Robot Photographer
```

中文名：

```text
机器人摄影师
```

推荐 CLI：

```bash
agentic photo --real
```

单条命令模式：

```bash
agentic photo --real "拍一张工作区照片"
```

允许机械臂运动：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 agentic photo --real --allow-arm-motion
```

Robot Photographer 的任务：

- 通过自然语言理解用户的拍摄意图。
- 把意图转换成受限、可校验的 `PhotoPlan`。
- 通过 AgenticOS Runtime/Kernel 执行已校验 plan。
- 使用真实相机保存 PNG + metadata。
- 只允许 allowlist 中的安全机械臂动作和受控相机姿态。
- 支持中心、左右偏航、上下俯仰的多角度拍摄，并用确定性图像指标验证差异。
- 写入 evidence、session、audit 和 memory。

## 2. 不可破坏的真实机器人边界

必须保留当前 AgenticOS 机器人安全边界。

- Agent App 不能 import `rclpy`。
- Agent App 不能直接订阅 camera topic。
- Agent App 不能直接发布 servo topic。
- Agent App 不能直接调用 MoveIt、Nav2、kinematics、`/cmd_vel`、`/scan`、`/odom` 或 `/tf`。
- Runtime / SDK 不能 import `rclpy`。
- 只有 `/home/ubuntu/agentic_ws/ros2_bridge_src/*` 下的 ROS2 bridge package 可以 import `rclpy`。
- 真实运动必须经过 permission、safety check、resource lock、bridge allowlist、timeout 和 audit log。
- LLM / VLM 不能执行实时闭环控制。
- 不添加 Gazebo、gz、fake Nav2、RViz-only demo 或 fake success。
- 不修改 `/opt/ros`、MoveIt、Nav2 或 vendor drivers。

## 3. AIOS/Cerebrum App 形态

AgenticOS 参考 agiresearch/AIOS 的思想：Agent App 应该是一个可加载、可运行、可发布的 agent package。Robot Photographer 应支持 AIOS/Cerebrum 风格入口：

```text
RobotPhotographerAgent.run(task_input)
```

同时，机器人权限、安全、资源锁、审计、ROS2 bridge、HAL 都不属于 App 直接控制范围，必须由 AgenticOS Runtime/Kernel 处理。

推荐目录：

```text
/home/ubuntu/agentic_ws/src/robot_photographer_agent/
  config.json
  entry.py
  meta_requirements.txt
  app.yaml
  main.py
  planner.py
  validation.py
  schemas/
    photo_plan.schema.json
    photo_result.schema.json
  policies/
    robot_photographer.policy.yaml
  workflows/
    default.yaml
  prompts/
    intent_parser.system.md
  tests/
    test_aios_manifest.py
    test_entry_loads.py
    test_plan_validation.py
    test_no_rclpy_import.py
    test_policy_rejects_unsafe_motion.py
```

Agentic APP 组成：

```text
Agentic APP 组成
- config.json
- entry.py
- meta_requirements.txt
- app.yaml
- prompts/
- schemas/
- workflows/
- policies/
- tests/
```

不要把全局 LLM、memory manager、tool manager、storage manager、world model、device arbitration 写成 App 本体。App 只能声明依赖它们；它们由 AgenticOS Runtime/Kernel 拥有和调度。

## 4. `config.json`：AIOS/Cerebrum App Manifest

`config.json` 描述“这个 Agent App 是什么”，用于 AIOS/Cerebrum 风格加载、发布和运行。

推荐内容：

```json
{
  "name": "robot_photographer_agent",
  "description": "A real-robot photography Agent App running on AgenticOS. It captures workspace photos and may execute only allowlisted named camera-arm motions through AgenticOS-safe capabilities.",
  "tools": [
    "agenticos/perception_capture_photo",
    "agenticos/arm_move_named",
    "agenticos/robot_stop",
    "agenticos/robot_status",
    "agenticos/recent_photos"
  ],
  "meta": {
    "author": "AgenticOS",
    "version": "0.1.0",
    "license": "Proprietary"
  },
  "build": {
    "entry": "entry.py",
    "module": "RobotPhotographerAgent"
  }
}
```

规则：

- `config.json` 不能声明 ROS2 topic / service / action。
- `tools` 只能声明 AgenticOS tool wrapper。
- tool wrapper 只能调用 AgenticOS Runtime/SDK/system call，不能 import ROS 或接触硬件。
- `build.module` 必须能加载 `RobotPhotographerAgent`。

## 5. `app.yaml`：机器人权限与安全 Manifest

`app.yaml` 描述“这个 Agent App 在机器人上被允许做什么”。它是 AgenticOS Runtime/Kernel 的安全输入，不替代 `config.json`。

推荐内容：

```yaml
name: robot_photographer_agent
version: 0.1.0
description: AIOS-compatible AgenticOS-safe real robot photography agent.
runtime_type: aios_agent_package
entrypoint: entry:RobotPhotographerAgent
executor_entrypoint: main:execute_plan

required_capabilities:
  - robot.get_state
  - robot.stop
  - perception.capture_photo
  - arm.get_state
  - arm.move_named
  - storage.list_recent_photos
  - memory.remember
  - memory.recall
  - report.say

permissions:
  - robot.state.read
  - robot.stop
  - perception.capture
  - arm.state.read
  - arm.move.named
  - storage.read
  - memory.read
  - memory.write
  - report.say

resources:
  - camera
  - arm
  - photo_verifier

allowed_targets:
  - workspace

allowed_arm_actions:
  - camera_center
  - camera_yaw_left_15
  - camera_yaw_right_15
  - camera_pitch_up_15
  - camera_pitch_down_15
  - arm_home

limits:
  burst_count_max: 5
  burst_interval_s_max: 5
  arm_action_timeout_s_max: 8
  capture_timeout_s_max: 5
  multi_angle_pose_count_max: 5
  min_image_difference_score: 0.08

motion_confirmation_policy:
  motion_disabled_by_default: true
  allow_env: AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION
  allow_cli_flag: --allow-arm-motion
  require_confirmation_unless_cli_flag: --yes

evidence:
  root: /opt/agentic/var/evidence/photos

safety_policy:
  allow_autonomous_navigation: false
  allow_arbitrary_joint_targets: false
  allow_cartesian_trajectories: false
  allow_freeform_grasping: false
  allow_base_motion: false
  stop_on_human_request: true
```

## 6. AIOS Tool 与 AgenticOS Capability 分层

Robot Photographer 需要同时兼容 AIOS/Cerebrum 的 tool 声明方式和 AgenticOS 的机器人安全能力模型。

分层定义：

```text
AIOS Tool
  -> AgenticOS tool wrapper
  -> AgenticOS Runtime/SDK/system call
  -> AgenticOS Capability / Skill
  -> permission + safety + resource lock + audit
  -> ROS2 Bridge / HAL
  -> ROS2
  -> robot hardware
```

职责边界：

- AIOS Tool 是 Agent App 可声明、可调用的工具接口。
- AgenticOS tool wrapper 是 tool 的本地适配层，只能调用 Runtime/SDK/system call。
- AgenticOS Capability / Skill 是带权限、安全、资源锁、审计的 OS 能力。
- ROS2 Bridge / HAL 是 capability 的硬件后端。
- tool wrapper 不能 import `rclpy`。
- tool wrapper 不能直接调用 ROS2 topic / service / action。
- tool wrapper 不能绕过 Runtime/Kernel 调硬件。

推荐 tool wrapper 名称：

```text
agenticos/perception_capture_photo -> perception.capture_photo
agenticos/arm_move_named           -> arm.move_named
agenticos/robot_stop               -> robot.stop
agenticos/robot_status             -> robot.get_state + arm.get_state
agenticos/recent_photos            -> storage.list_recent_photos
```

## 7. Plan-first 架构

Robot Photographer 不允许普通 AIOS Agent 中常见的直接链路：

```text
LLM -> tool call -> tool.run() -> hardware
```

必须使用 plan-first 架构：

```text
user task
  -> planner LLM 或 rule fallback
  -> bounded photo plan
  -> schema validation
  -> policy validation
  -> risk classification
  -> confirmation gate
  -> deterministic executor
  -> AgenticOS system calls
  -> Runtime permission / safety / resource lock / audit
  -> ROS2 bridge / HAL
  -> hardware
```

关键约束：

- planner 只输出 JSON plan。
- plan 在 validation 前不能触发任何 tool 或硬件。
- validator 把 LLM 输出视为不可信输入。
- deterministic executor 只接受已校验 plan。
- executor 不处理原始自然语言。
- executor 不调用 LLM。
- 硬件动作只通过 AgenticOS system call。

## 8. `entry.py` 设计

`entry.py` 是 AIOS/Cerebrum 风格入口，定义 `RobotPhotographerAgent`。

职责：

1. 接收 `run(task_input)`。
2. 调用 `planner.py`，把自然语言或结构化 task 转成 bounded plan。
3. 调用 `validation.py`，校验 schema、policy、risk class、权限和确认要求。
4. 调用 `main.py` deterministic executor 执行已校验 plan。
5. 返回结构化结果。

禁止：

- 不能 import `rclpy`。
- 不能 import ROS2 message / service / action types。
- 不能订阅 camera topic。
- 不能发布 servo topic。
- 不能直接调用 ROS2 service / action。
- 不能直接控制硬件。

伪代码：

```python
class RobotPhotographerAgent:
    def __init__(self, agent_name: str = "robot_photographer_agent", runtime=None):
        self.agent_name = agent_name
        self.runtime = runtime

    def run(self, task_input):
        plan = planner.plan_task(task_input)
        validated_plan = validation.validate_plan(
            plan,
            policy_path="policies/robot_photographer.policy.yaml",
            schema_path="schemas/photo_plan.schema.json",
        )
        return main.execute_plan(validated_plan, runtime=self.runtime)
```

`run(task_input)` 输入可为：

```json
{
  "text": "把相机抬起来再拍一张",
  "allow_arm_motion": true,
  "assume_yes": true,
  "target": "workspace"
}
```

也可为单纯字符串：

```text
拍一张照片
```

## 9. `planner.py` 设计

planner 负责把用户任务转换为 `PhotoPlan`。

planner mode：

```text
llm
rule_based
```

Robot Photographer 使用 **LLM-first + rule fallback**：

1. 只有 `AGENTIC_LLM_ENABLED=1` 且 Runtime LLM 配置和 secret 可用时才调用 LLM。
2. LLM provider 由 AgenticOS Runtime 拥有，App 只使用 Runtime 的 OpenAI-compatible client。
3. 默认 provider 为 Yunwu，默认 base URL 为 `https://yunwu.ai/v1`，client 拼接 `/chat/completions`。
4. 默认模型为 `gpt-4o-mini`，可通过 `AGENTIC_LLM_MODEL` 或 `/opt/agentic/etc/models.yaml` 修改。
5. API key 只能从环境变量 `AGENTIC_LLM_API_KEY` 或 `/opt/agentic/etc/secrets/yunwu.env` 读取。
6. LLM 只允许输出 `photo_plan.schema.json` 兼容 JSON object，不能输出 markdown fence、解释文本、代码或工具调用。
7. LLM 输出必须继续经过 schema validation、policy validation、risk classification、confirmation gate。
8. LLM 超时、网络失败、非 JSON、markdown fence、响应结构异常或 schema invalid 时，planner 回退到 rule_based。
9. 如果 LLM 输出 schema 合法但违反 policy、motion permission、confirmation 或 risk classification，validator 返回结构化错误，不执行 executor。
10. deterministic executor 不调用 LLM，也不处理自然语言。

Runtime LLM 配置：

```yaml
models:
  default_reasoning_model:
    provider: yunwu
    base_url: https://yunwu.ai/v1
    model: gpt-4o-mini
    timeout_s: 20
    temperature: 0
    max_tokens: 800
    enabled: true
```

secret 位置：

```text
/opt/agentic/etc/secrets/yunwu.env
```

secret 文件只能包含本机私密配置，不能把真实 key 写进源码、测试或文档示例。

LLM planner system prompt 存放：

```text
prompts/intent_parser.system.md
```

system prompt 必须包含：

```text
Return exactly one raw JSON object.
Do not wrap it in markdown.
Do not call tools, code, robot middleware, drivers, or hardware.
Convert user language into a bounded photography plan using only allowed intents, allowed targets, and allowed action names.
```

rule fallback 至少识别：

- `拍照`、`照片`、`图片`、`看一下` -> `capture_photo`
- `连续`、`连拍`、`三张` -> `capture_burst`
- `抬起相机`、`camera up` -> `move_camera_pose` + `camera_pitch_up_15` + `capture_photo`
- `多角度`、`不同角度`、`左右上下` -> `multi_angle_capture`
- `验证不一样`、`确认不同` -> 添加 `verify_photo_differences`
- `回到初始`、`arm home` -> `arm_home`
- `最近照片` -> `recent_photos`
- `状态` -> `status`
- `停止`、`取消`、`stop` -> `stop`

## 10. `validation.py` 设计

validation 负责：

- JSON schema validation。
- policy validation。
- risk classification。
- motion permission validation。
- confirmation gate validation。
- fake success rejection。
- no unsupported step validation。

validator 输入：

```text
plan
policy
runtime flags:
  allow_arm_motion
  assume_yes
environment:
  AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION
```

validator 输出：

```text
ValidatedPhotoPlan
```

或结构化错误：

```text
PHOTO_PLAN_INVALID
PHOTO_INTENT_UNSUPPORTED
PHOTO_STEP_UNSUPPORTED
PHOTO_RISK_CLASS_INVALID
ARM_MOTION_DISABLED
ARM_CONFIRMATION_REQUIRED
ARM_ACTION_NOT_ALLOWED
PHOTO_COUNT_LIMIT_EXCEEDED
PHOTO_INTERVAL_LIMIT_EXCEEDED
TARGET_NOT_ALLOWED
```

## 11. `main.py`：Deterministic Executor

`main.py` 不再处理原始自然语言。它只执行已校验的 plan。

职责：

- 接收 `ValidatedPhotoPlan`。
- 顺序执行 plan steps。
- 只调用 AgenticOS SDK / system call / capability wrapper。
- 收集 step result。
- 写 evidence / memory integration。
- 返回结构化 `PhotoResult`。

禁止：

- 不调用 LLM。
- 不解析自然语言。
- 不 import `rclpy`。
- 不直接调用 ROS2。
- 不让 LLM 输出直接触发硬件。

支持 step types：

```text
capture_photo
arm_named_action
recent_photos
status
stop
sleep
```

伪代码：

```python
async def execute_plan(ctx, plan):
    results = []
    for step in plan["steps"]:
        if step["type"] == "capture_photo":
            results.append(await ctx.perception.capture_photo(...))
        elif step["type"] == "arm_named_action":
            results.append(await ctx.arm.move_named(...))
        elif step["type"] == "recent_photos":
            results.append(await ctx.storage.list_recent_photos(...))
        elif step["type"] == "status":
            results.append({
                "robot": await ctx.robot.get_state(),
                "arm": await ctx.arm.get_state(),
            })
        elif step["type"] == "stop":
            results.append(await ctx.robot.stop(...))
        elif step["type"] == "sleep":
            await asyncio.sleep(step["duration_s"])
    return build_photo_result(plan, results)
```

## 12. Photo Plan Schema

文件：

```text
schemas/photo_plan.schema.json
```

最小 schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Robot Photographer Photo Plan",
  "type": "object",
  "required": [
    "schema_version",
    "plan_id",
    "intent",
    "risk_class",
    "requires_motion",
    "needs_confirmation",
    "planner_mode",
    "steps",
    "user_summary"
  ],
  "properties": {
    "schema_version": {"const": "1.0"},
    "plan_id": {"type": "string", "minLength": 1},
    "intent": {
      "type": "string",
      "enum": [
        "capture_photo",
        "capture_burst",
        "move_camera_pose",
        "arm_home",
        "before_after_capture",
        "recent_photos",
        "status",
        "stop",
        "unsupported"
      ]
    },
    "risk_class": {
      "type": "string",
      "enum": ["read_only", "named_motion", "emergency_control"]
    },
    "requires_motion": {"type": "boolean"},
    "needs_confirmation": {"type": "boolean"},
    "planner_mode": {"type": "string", "enum": ["llm", "rule_based"]},
    "target": {"type": "string", "enum": ["workspace"]},
    "steps": {
      "type": "array",
      "minItems": 1,
      "maxItems": 12,
      "items": {
        "type": "object",
        "required": ["type"],
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "capture_photo",
              "arm_named_action",
              "verify_photo_differences",
              "recent_photos",
              "status",
              "stop",
              "sleep"
            ]
          },
          "target": {"type": "string", "enum": ["workspace"]},
          "label": {"type": "string"},
          "name": {
            "type": "string",
            "enum": [
              "arm_home",
              "camera_center",
              "camera_yaw_left_15",
              "camera_yaw_right_15",
              "camera_pitch_up_15",
              "camera_pitch_down_15"
            ]
          },
          "timeout_s": {"type": "integer", "minimum": 1, "maximum": 8},
          "count": {"type": "integer", "minimum": 1, "maximum": 5},
          "duration_s": {"type": "number", "minimum": 0, "maximum": 5},
          "limit": {"type": "integer", "minimum": 1, "maximum": 20},
          "reason": {"type": "string"},
          "method": {"type": "string", "enum": ["deterministic_cv_metrics"]},
          "min_difference_score": {"type": "number", "minimum": 0.0, "maximum": 1.0}
        },
        "additionalProperties": false
      }
    },
    "user_summary": {"type": "string"}
  },
  "additionalProperties": false
}
```

示例 plan：

```json
{
  "schema_version": "1.0",
  "plan_id": "plan_capture_001",
  "intent": "capture_photo",
  "risk_class": "read_only",
  "requires_motion": false,
  "needs_confirmation": false,
  "planner_mode": "rule_based",
  "target": "workspace",
  "steps": [
    {
      "type": "capture_photo",
      "target": "workspace",
      "label": "photo",
      "timeout_s": 5
    }
  ],
  "user_summary": "拍摄一张工作区照片"
}
```

motion plan：

```json
{
  "schema_version": "1.0",
  "plan_id": "plan_camera_pitch_up_001",
  "intent": "move_camera_pose",
  "risk_class": "named_motion",
  "requires_motion": true,
  "needs_confirmation": true,
  "planner_mode": "llm",
  "target": "workspace",
  "steps": [
    {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "after_pitch_up_15", "timeout_s": 5}
  ],
  "user_summary": "抬起相机后拍摄一张工作区照片"
}
```

## 13. Photo Result Schema

文件：

```text
schemas/photo_result.schema.json
```

最小字段：

```json
{
  "schema_version": "1.0",
  "success": true,
  "plan_id": "plan_capture_001",
  "session_id": "sess_xxx",
  "audit_ids": ["audit_xxx"],
  "steps": [
    {
      "type": "capture_photo",
      "success": true,
      "image_path": "/opt/agentic/var/evidence/photos/photo_....png",
      "metadata_path": "/opt/agentic/var/evidence/photos/photo_....json",
      "topic": "/depth_cam/rgb0/image_raw",
      "width": 640,
      "height": 400,
      "encoding": "bgr8"
    }
  ],
  "error_code": "",
  "reason": ""
}
```

失败时：

```json
{
  "schema_version": "1.0",
  "success": false,
  "plan_id": "plan_capture_001",
  "session_id": "sess_xxx",
  "audit_ids": ["audit_xxx"],
  "steps": [],
  "error_code": "CAMERA_UNAVAILABLE",
  "reason": "No fresh camera frame received."
}
```

## 14. Policy 文件

文件：

```text
policies/robot_photographer.policy.yaml
```

推荐内容：

```yaml
policy_version: "1.0"
name: robot_photographer_policy

targets:
  allowed:
    - workspace

read_only:
  capture_photo_allowed_by_default: true

motion:
  disabled_by_default: true
  allow_env: AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION
  allow_cli_flag: --allow-arm-motion
  require_confirmation: true
  confirmation_bypass_cli_flag: --yes
  allowed_named_actions:
    - arm_home
    - camera_center
    - camera_yaw_left_15
    - camera_yaw_right_15
    - camera_pitch_up_15
    - camera_pitch_down_15
  disallowed:
    arbitrary_joint_targets: true
    cartesian_trajectories: true
    freeform_grasping: true
    base_motion: true
    direct_servo_pulses_from_app: true
  arm_action_timeout_s_max: 8

burst:
  count_max: 5
  interval_s_max: 5

multi_angle:
  max_pose_count: 5
  require_return_home_after_sequence: true
  require_difference_verification: true
  min_image_difference_score: 0.08

capture:
  timeout_s_max: 5

evidence:
  root: /opt/agentic/var/evidence/photos
  require_metadata: true
  require_index: true
```

策略语义：

- read-only photo 默认允许。
- motion 默认拒绝。
- motion 只有 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 或 CLI `--allow-arm-motion` 时允许。
- motion 需要确认，除非传入 `--yes`。
- 不允许任意关节目标。
- 不允许笛卡尔轨迹。
- 不允许自由抓取。
- 不允许底盘移动。
- arm action timeout `<= 8s`。
- burst count `<= 5`。
- burst interval `<= 5s`。
- target allowlist 只有 `workspace`。
- 多角度拍摄最多 5 个相机姿态，必须回到 `arm_home`，并生成 verification JSON。

## 15. Agentic System Call Contract

Agent App 访问 AgenticOS Kernel capability 的唯一接口是 AgenticOS SDK / system call / tool wrapper。App 不能绕过这些接口。

### 15.1 `perception.capture_photo`

用途：保存真实相机图片和 metadata。

input：

```json
{
  "target": "workspace",
  "label": "photo",
  "timeout_s": 5,
  "request_id": "capture_xxx"
}
```

output：

```json
{
  "success": true,
  "image_path": "/opt/agentic/var/evidence/photos/photo_....png",
  "metadata_path": "/opt/agentic/var/evidence/photos/photo_....json",
  "evidence_json": "{}",
  "error_code": "",
  "reason": ""
}
```

permission：

```text
perception.capture
```

resource lock：

```text
camera
```

backend：

```text
ROS2 service /agentic/perception/capture_photo
agentic_msgs/srv/CapturePhoto
```

structured errors：

```text
CAMERA_UNAVAILABLE
CAMERA_FRAME_STALE
CAPTURE_ENCODING_UNSUPPORTED
CAPTURE_WRITE_FAILED
CAPTURE_TIMEOUT
AGENTIC_BRIDGE_UNAVAILABLE
```

### 15.2 `arm.move_named`

用途：执行 allowlist 中的命名机械臂动作。

input：

```json
{
  "name": "camera_pitch_up_15",
  "timeout_s": 8,
  "request_id": "arm_xxx"
}
```

output：

```json
{
  "success": true,
  "name": "camera_pitch_up_15",
  "result_json": "{}",
  "error_code": "",
  "reason": ""
}
```

permission：

```text
arm.move.named
```

resource lock：

```text
arm
```

backend：

```text
ROS2 action /agentic/arm/move_named
agentic_msgs/action/MoveArmNamed
```

structured errors：

```text
ARM_MOTION_DISABLED
ARM_CONFIRMATION_REQUIRED
ARM_ACTION_NOT_ALLOWED
ARM_TIMEOUT_LIMIT_EXCEEDED
ARM_BUSY
ARM_ACTION_TIMEOUT
BACKEND_UNAVAILABLE
CAMERA_POSE_BACKEND_MISSING
ARM_ACTION_BACKEND_MISSING
STOP_BACKEND_UNAVAILABLE
```

### 15.3 `robot.stop`

用途：停止或取消 active robot / arm action。

input：

```json
{
  "reason": "operator_requested_from_robot_photographer",
  "request_id": "stop_xxx"
}
```

output：

```json
{
  "success": true,
  "message": "{}",
  "error_code": ""
}
```

permission：

```text
robot.stop
```

resource lock：

```text
stop is emergency/control path and must not be blocked by normal resource locks
```

backend：

```text
ROS2 service /agentic/robot/stop
agentic_msgs/srv/StopRobot
then /agentic/arm/stop when active arm action exists
```

structured errors：

```text
STOP_BACKEND_UNAVAILABLE
STOP_BACKEND_TIMEOUT
STOP_BACKEND_UNIMPLEMENTED
AGENTIC_BRIDGE_UNAVAILABLE
```

### 15.4 `robot.get_state`

用途：读取机器人状态。

input：

```json
{}
```

output：

```json
{
  "success": true,
  "robot_id": "rosorin_real_robot",
  "mode": "real",
  "estop_pressed": false,
  "is_moving": false
}
```

permission：

```text
robot.state.read
```

resource lock：

```text
none
```

backend：

```text
ROS2 service /agentic/robot/get_state
agentic_msgs/srv/GetRobotState
```

structured errors：

```text
ROBOT_STATE_UNAVAILABLE
AGENTIC_BRIDGE_UNAVAILABLE
```

### 15.5 `storage.list_recent_photos`

用途：读取最近照片 index。

input：

```json
{
  "limit": 5
}
```

output：

```json
{
  "success": true,
  "photos": [
    {
      "image_path": "/opt/agentic/var/evidence/photos/photo_....png",
      "metadata_path": "/opt/agentic/var/evidence/photos/photo_....json",
      "created_unix": 0.0
    }
  ]
}
```

permission：

```text
storage.read
```

resource lock：

```text
none or storage_read
```

backend：

```text
Runtime storage manager reads /opt/agentic/var/evidence/photos/index.jsonl
```

structured errors：

```text
PHOTO_INDEX_UNAVAILABLE
PHOTO_INDEX_CORRUPT
STORAGE_READ_FAILED
```

### 15.6 `photo.verify_differences`

用途：在 deterministic executor 中读取已保存 PNG 和 metadata，验证多角度照片是否确实不同。这个步骤不访问 ROS，不控制硬件，也不调用 LLM/VLM。

input：

```json
{
  "plan_id": "plan_xxx",
  "capture_results": [
    {"image_path": "/opt/agentic/var/evidence/photos/center.png", "metadata_path": "/opt/agentic/var/evidence/photos/center.json"}
  ],
  "method": "deterministic_cv_metrics",
  "min_difference_score": 0.08
}
```

output：

```json
{
  "success": true,
  "verification_path": "/opt/agentic/var/evidence/photos/verification_plan_xxx.json",
  "min_pair_difference_score": 0.21,
  "max_pair_difference_score": 0.54,
  "pairs": []
}
```

permission：

```text
storage.read
```

resource lock：

```text
photo_verifier
```

backend：

```text
deterministic OpenCV/numpy image metrics inside Robot Photographer executor
```

structured errors：

```text
PHOTO_VERIFICATION_BACKEND_INCOMPLETE
PHOTO_VERIFICATION_IMAGE_MISSING
PHOTO_VERIFICATION_READ_FAILED
PHOTO_VERIFICATION_NO_IMAGES
PHOTO_DIFFERENCE_TOO_SMALL
```

## 16. 真实机器人环境

使用当前部署阶段已经发现的真实机器人环境：

- AgenticOS 安装根目录：`/opt/agentic`
- Agent App 工作区：`/home/ubuntu/agentic_ws/src`
- AgenticOS bridge 源码目录：`/home/ubuntu/agentic_ws/ros2_bridge_src`
- Runtime 源码目录：`/home/ubuntu/agentic_ws/src/agentic_runtime_src`
- 相机 topic：`/depth_cam/rgb0/image_raw`
- 相机 frame：`rgb_camera_link`
- 已观测图像：`640x400 bgr8`
- 机械臂后端：`servo_action_group`
- servo 命令 topic：`/servo_controller`
- 安全 action group 文件：
  - `/home/ubuntu/software/arm_pc/ActionGroups/init.d6a`
  - `/home/ubuntu/software/arm_pc/ActionGroups/horizontal.d6a`
  - `/home/ubuntu/software/arm_pc/ActionGroups/detect_left.d6a`
  - `/home/ubuntu/software/arm_pc/ActionGroups/detect_right.d6a`
  - `/home/ubuntu/software/arm_pc/ActionGroups/camera_up.d6a`
  - `/home/ubuntu/software/arm_pc/ActionGroups/left_down.d6a`
- 允许的命名机械臂动作：
  - `arm_home` -> 后端动作 `init`
  - `camera_center` -> 后端动作 `horizontal`
  - `camera_yaw_left_15` -> 后端动作 `detect_left`
  - `camera_yaw_right_15` -> 后端动作 `detect_right`
  - `camera_pitch_up_15` -> 后端动作 `camera_up`
  - `camera_pitch_down_15` -> 后端动作 `left_down`
- 如果任一后端 action group 文件缺失，bridge 必须返回 `CAMERA_POSE_BACKEND_MISSING` 或 `ARM_ACTION_BACKEND_MISSING`，不能 fake success。
- bridge 拥有动作执行权时的 stop 后端：
  - `ActionGroupController.stop_action_group`

bridge profile：

```text
/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml
```

## 17. 面向用户的能力

### 17.1 单张拍照

自然语言：

```text
拍一张照片
拍一下
拍一下工作区
拍一张 workspace 的照片
```

plan：

```json
{
  "intent": "capture_photo",
  "risk_class": "read_only",
  "steps": [
    {"type": "capture_photo", "target": "workspace", "label": "photo", "timeout_s": 5}
  ]
}
```

### 17.2 抬起相机后拍照

自然语言：

```text
把相机抬高一点再拍
相机抬起来拍一张
camera up and take a photo
```

plan：

```json
{
  "intent": "move_camera_pose",
  "risk_class": "named_motion",
  "requires_motion": true,
  "needs_confirmation": true,
  "steps": [
    {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "after_pitch_up_15", "timeout_s": 5}
  ]
}
```

需要：

```text
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1
```

或：

```text
--allow-arm-motion
```

并需要确认，除非：

```text
--yes
```

### 17.3 机械臂回初始位

```json
{
  "intent": "arm_home",
  "risk_class": "named_motion",
  "steps": [
    {"type": "arm_named_action", "name": "arm_home", "timeout_s": 8}
  ]
}
```

### 17.4 连拍

约束：

- 默认张数：`3`
- 最大张数：`5`
- 默认间隔：`0.5s`
- 最大间隔：`5s`

### 17.5 前后对比拍照

计划：

```text
capture_photo(label="before")
arm.move_named("camera_pitch_up_15")
capture_photo(label="after_pitch_up_15")
write comparison.json
```

需要 motion permission 和 confirmation。

### 17.6 多角度拍摄并验证差异

自然语言：

```text
拍一组多角度照片
左右上下都拍一下，并确认照片不一样
```

plan：

```json
{
  "intent": "multi_angle_capture",
  "risk_class": "named_motion",
  "requires_motion": true,
  "needs_confirmation": true,
  "steps": [
    {"type": "arm_named_action", "name": "camera_center", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "center", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_yaw_left_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "yaw_left_15", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_yaw_right_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "yaw_right_15", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "pitch_up_15", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_pitch_down_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "pitch_down_15", "timeout_s": 5},
    {"type": "verify_photo_differences", "method": "deterministic_cv_metrics", "min_difference_score": 0.08},
    {"type": "arm_named_action", "name": "arm_home", "timeout_s": 8}
  ]
}
```

执行要求：

- 必须通过 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 或 `--allow-arm-motion`。
- 交互模式需要用户确认，除非 `--yes`。
- LLM 只能生成 bounded JSON plan，不能直接调用工具、ROS 或硬件。
- deterministic executor 只执行已通过 schema/policy/risk/confirmation 的 plan。
- verification JSON 写入 `/opt/agentic/var/evidence/photos/verification_<plan_id>.json`。

### 17.7 最近照片

读取：

```text
/opt/agentic/var/evidence/photos/index.jsonl
```

默认 `limit=5`。

### 17.8 状态

读取：

```text
robot.get_state
arm.get_state
storage.list_recent_photos
```

### 17.8 停止

调用：

```text
robot.stop(reason="operator_requested_from_robot_photographer")
```

## 18. `perception.capture_photo` 纵向链路

保留并实现完整拍照能力。

### 18.1 AgenticOS Capability

新增：

```text
perception.capture_photo
```

SDK：

```python
photo = await ctx.perception.capture_photo(
    target="workspace",
    label="photo",
    timeout_s=5,
)
```

skill manifest：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/skills/perception_capture_photo.yaml
```

要求：

- permission：`perception.capture`
- resource lock：`camera`
- safety：target allowlist、timeout limit、read-only capture allowed
- audit：必须写 audit
- backend：`/agentic/perception/capture_photo`

### 18.2 ROS2 Contract

新增：

```text
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_msgs/srv/CapturePhoto.srv
```

内容：

```text
string target
string label
string request_id
int32 timeout_s
---
bool success
string error_code
string reason
string image_path
string metadata_path
string evidence_json
```

### 18.3 Bridge 实现

在 AgenticOS bridge 层实现：

```text
/agentic/perception/capture_photo
```

首选文件：

```text
/home/ubuntu/agentic_ws/ros2_bridge_src/agentic_capability_bridge/agentic_capability_bridge/inspection_bridge_node.py
```

bridge 可以 import：

- `rclpy`
- `sensor_msgs/msg/Image`
- `cv2`
- `numpy`

bridge 必须：

1. 从 `/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml` 读取 camera 配置。
2. 订阅 `/depth_cam/rgb0/image_raw`。
3. 保留 latest fresh frame。
4. 收到 `CapturePhoto` 请求时检查 freshness。
5. 支持 encoding：
   - `bgr8`
   - `rgb8`
   - `mono8`
   - `8UC1`
   - 可选 `bgra8` / `rgba8`
6. 保存 PNG：
   ```text
   /opt/agentic/var/evidence/photos/photo_<timestamp>_<request_id>.png
   ```
7. 保存 metadata JSON。
8. 追加：
   ```text
   /opt/agentic/var/evidence/photos/index.jsonl
   ```
9. 返回真实结构化错误，不能 fake success。

metadata 包含：

```json
{
  "target": "workspace",
  "label": "photo",
  "request_id": "capture_xxx",
  "topic": "/depth_cam/rgb0/image_raw",
  "frame_id": "rgb_camera_link",
  "stamp": {"sec": 0, "nanosec": 0},
  "height": 400,
  "width": 640,
  "encoding": "bgr8",
  "step": 1920,
  "data_length": 768000,
  "image_path": "/opt/agentic/var/evidence/photos/photo_....png",
  "metadata_path": "/opt/agentic/var/evidence/photos/photo_....json",
  "received_unix": 0.0
}
```

### 18.4 Runtime / SDK

更新：

```text
agentic_runtime/sdk/perception.py
agentic_runtime/ros_bridge_client/types.py
agentic_runtime/ros_bridge_client/client.py
agentic_runtime/ros_bridge_client/cli_client.py
agentic_runtime/ros_bridge_client/mock_client.py
agentic_runtime/skill_executor/dispatcher.py
agentic_runtime/types.py
configs/permissions.yaml
configs/capabilities.yaml
configs/safety.yaml
```

Runtime 不得 import `rclpy`，只能通过 bridge client 调用。

## 19. Evidence 布局

使用：

```text
/opt/agentic/var/evidence/photos/
```

文件：

```text
photo_20260614_153022_capture_abc123.png
photo_20260614_153022_capture_abc123.json
index.jsonl
shot_set_20260614_153030.json
comparison_20260614_153045.json
```

index entry：

```json
{
  "kind": "photo",
  "image_path": "/opt/agentic/var/evidence/photos/photo_....png",
  "metadata_path": "/opt/agentic/var/evidence/photos/photo_....json",
  "target": "workspace",
  "label": "photo",
  "topic": "/depth_cam/rgb0/image_raw",
  "width": 640,
  "height": 400,
  "encoding": "bgr8",
  "session_id": "sess_xxx",
  "audit_ids": ["audit_xxx"],
  "created_unix": 0.0
}
```

## 20. 详细执行流程

### 20.1 单张拍照

```text
用户: 拍一张照片
```

流程：

1. `agentic photo --real` 接收 text。
2. CLI 构造 `task_input`。
3. AIOS loader 加载 `config.json` 和 `entry.py`。
4. 调用 `RobotPhotographerAgent.run(task_input)`。
5. `entry.py` 调用 planner。
6. planner 输出 `PhotoPlan`。
7. validator 做 schema validation。
8. validator 做 policy validation。
9. validator 标记 risk class：`read_only`。
10. validator 通过 confirmation gate。
11. executor 执行 `capture_photo` step。
12. executor 调用 `perception.capture_photo` system call。
13. Runtime 检查 permission `perception.capture`。
14. Runtime 调用 safety guard。
15. Runtime 锁定 `camera`。
16. Runtime 调用 bridge `/agentic/perception/capture_photo`。
17. bridge 保存 PNG + metadata + index。
18. Runtime 解锁 `camera`。
19. Runtime 写 audit。
20. executor 返回 `PhotoResult`。
21. App 写 memory `last_photo`。
22. CLI 打印图片路径。

LLM 只允许在第 5-6 步生成 plan，不能进入第 11-22 步。

### 20.2 抬起相机后拍照

```text
用户: 把相机抬起来再拍一张
```

流程：

1. planner 输出 `risk_class=named_motion`。
2. validator 检查 `camera_pitch_up_15` 在 allowlist。
3. validator 检查 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 或 `--allow-arm-motion`。
4. validator 检查 confirmation，除非 `--yes`。
5. executor 调用 `arm.move_named("camera_pitch_up_15")`。
6. Runtime 检查 permission `arm.move.named`。
7. Runtime 调用 safety guard。
8. Runtime 锁定 `arm`。
9. Runtime 调用 `/agentic/arm/move_named`。
10. bridge 执行 profile 映射的后端 action group `camera_up.d6a`。
11. Runtime 解锁 `arm`。
12. executor 调用 `perception.capture_photo`。
13. bridge 保存 PNG + metadata。
14. 返回 result。

### 20.3 多角度拍摄并验证

```text
用户: 拍一组多角度照片并确认不一样
```

流程：

1. planner LLM 或 rule fallback 输出 `intent=multi_angle_capture` 的 bounded JSON plan。
2. plan 只能包含 `camera_center`、`camera_yaw_left_15`、`camera_yaw_right_15`、`camera_pitch_up_15`、`camera_pitch_down_15` 和 `arm_home`。
3. validator 做 schema validation，拒绝任意角度、任意关节、笛卡尔轨迹、servo pulse 或底盘移动字段。
4. validator 做 policy validation，确认 pose 数量 `<= 5`、target 为 `workspace`、超时 `<= 8s`。
5. validator 检查 motion permission 和 confirmation gate。
6. executor 按顺序执行每个 `arm_named_action`，每一步都经 Runtime permission / safety / resource lock / audit。
7. bridge 根据 profile 把受控名映射到真实 `.d6a` 文件；文件缺失时返回 `CAMERA_POSE_BACKEND_MISSING` 或 `ARM_ACTION_BACKEND_MISSING`。
8. 每个姿态后 executor 调用 `perception.capture_photo` 保存 PNG + metadata。
9. executor 执行 `verify_photo_differences`，读取前面成功的 capture results。
10. verifier 用 OpenCV/numpy 计算 `mean_abs_diff`、`hist_distance`、`phash_distance` 和 `difference_score`。
11. verifier 写入 `/opt/agentic/var/evidence/photos/verification_<plan_id>.json`。
12. 如果图片缺失、读取失败、重复或任一成对差异低于阈值，返回结构化错误，不能 fake success。
13. executor 最后执行 `arm_home`，并返回结构化 `PhotoResult`。
14. Codex / 验收脚本抽样查看图片，确认中心、左、右、上、下视角在视觉上确实不同；如果不明显，报告 `ANGLE_DIFFERENCE_NOT_VISUALLY_CONFIRMED`。

### 20.4 Stop

```text
用户: 停止
```

流程：

1. planner 或 rule parser 输出 `intent=stop`。
2. validator 标记 `risk_class=emergency_control`。
3. executor 调用 `robot.stop`。
4. Runtime 走 stop path，不被普通 lock 阻塞。
5. safety guard 转发 `/agentic/arm/stop`。
6. manipulation bridge 如有 active action，则调用 stop backend。
7. 返回 stop evidence。

stop 不需要 LLM。

## 21. CLI 设计

新增：

```text
agentic photo
```

源代码模块：

```text
agentic_runtime/photo_cli.py
```

CLI options：

```text
agentic photo [--real|--mock] [--json] [--allow-arm-motion] [--yes] [command...]
```

职责：

1. 加载 AgenticOS 环境。
2. 在 `--real` 模式下确保 bridge services 正在运行。
3. 构造 AIOS-compatible `task_input`。
4. 加载 `robot_photographer_agent/config.json`。
5. 加载 `entry.py` 中的 `RobotPhotographerAgent`。
6. 调用 `agent.run(task_input)`。
7. 打印结构化或人类可读结果。

交互式示例：

```text
Robot Photographer ready.
Camera: ready
Arm: ready
Motion permission: disabled
Target: workspace

photo> 拍一张照片
拍摄完成
图片: /opt/agentic/var/evidence/photos/photo_20260614_153022.png
metadata: /opt/agentic/var/evidence/photos/photo_20260614_153022.json
```

motion confirmation 示例：

```text
计划需要机械臂动作:
  - camera_pitch_up_15

风险等级: named_motion
预计时间: <= 8s
stop backend: available

是否执行？ yes/no
```

## 22. 错误码

必须返回结构化错误。

plan / policy：

```text
PHOTO_PLAN_INVALID
PHOTO_INTENT_UNSUPPORTED
PHOTO_STEP_UNSUPPORTED
PHOTO_RISK_CLASS_INVALID
TARGET_NOT_ALLOWED
ARM_MOTION_DISABLED
ARM_CONFIRMATION_REQUIRED
ARM_ACTION_NOT_ALLOWED
PHOTO_COUNT_LIMIT_EXCEEDED
PHOTO_INTERVAL_LIMIT_EXCEEDED
```

camera / capture：

```text
CAMERA_UNAVAILABLE
CAMERA_FRAME_STALE
CAPTURE_ENCODING_UNSUPPORTED
CAPTURE_WRITE_FAILED
CAPTURE_TIMEOUT
PHOTO_INDEX_UNAVAILABLE
```

runtime / bridge：

```text
AGENTIC_BRIDGE_UNAVAILABLE
SAFETY_BACKEND_TIMEOUT
PERMISSION_DENIED
RESOURCE_LOCK_TIMEOUT
AUDIT_WRITE_FAILED
```

arm / stop：

```text
ARM_TIMEOUT_LIMIT_EXCEEDED
ARM_BUSY
ARM_ACTION_TIMEOUT
BACKEND_UNAVAILABLE
STOP_BACKEND_UNAVAILABLE
STOP_BACKEND_TIMEOUT
STOP_BACKEND_UNIMPLEMENTED
```

禁止：

- 硬件 topic / service 缺失时报告成功。
- 相机 frame 不新鲜时报告成功。
- action group 文件缺失时报告成功。
- stop backend 缺失时假装 stop succeeded。

## 23. 测试要求

必须新增或更新：

- AIOS manifest load test：加载 `config.json`。
- `entry.py` module load test：加载 `RobotPhotographerAgent`。
- `RobotPhotographerAgent.run(task_input)` smoke test。
- plan schema validation test。
- unsafe motion rejection test。
- no-rclpy import guard。
- no direct ROS topic/action/service access guard。
- tool wrapper does not import ROS。
- motion requires env/flag and confirmation。
- read-only photo allowed。
- fake success rejection。
- evidence and audit existence test。
- `perception.capture_photo` skill registration test。
- SDK `capture_photo` test。
- CLI bridge client `capture_photo` test。
- mock bridge client `capture_photo` test。
- bridge build test。
- OpenAI-compatible LLM client config / request / JSON parsing test。
- LLM bad JSON fallback test。
- LLM schema invalid fallback test。
- schema-valid LLM motion rejected by policy / confirmation gate test。
- multi-angle plan schema validation test。
- verifier duplicate / low-difference rejection test。
- mock multi-angle execution writes verification JSON test。
- camera pose backend missing structured error test。
- read-only real photo acceptance。
- optional `camera_pitch_up_15 + photo` acceptance gated by `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1`。
- optional real multi-angle photo acceptance gated by both `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` and `--allow-arm-motion --yes`。

禁止导入 guard 应检查：

```text
robot_photographer_agent/**/*.py
agentic_runtime/**/*.py
```

不得出现：

```text
import rclpy
from rclpy
/cmd_vel
/scan
/odom
/tf
/servo_controller
/depth_cam/rgb0/image_raw
/kinematics
MoveIt
Nav2
```

例外：ROS2 bridge packages under `/home/ubuntu/agentic_ws/ros2_bridge_src/*`。

## 24. 验收命令

只读拍照：

```bash
agentic photo --real "拍一张照片"
```

期望：

```text
success: true
image_path: /opt/agentic/var/evidence/photos/*.png
metadata_path: /opt/agentic/var/evidence/photos/*.json
```

允许机械臂运动：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 agentic photo --real --allow-arm-motion --yes "把相机抬起来再拍一张"
```

期望：

```text
arm action camera_pitch_up_15 succeeded
photo capture succeeded
stop_available true
```

多角度真实拍摄：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 agentic photo --real --allow-arm-motion --yes "拍一组多角度照片并验证差异"
```

期望：

```text
success: true
verification_path: /opt/agentic/var/evidence/photos/verification_*.json
min_pair_difference_score >= 0.08
```

测试：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/run_tests.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/build_robot_bridge.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_camera_acceptance.sh
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_multi_angle_photo_acceptance.sh
AGENTIC_LLM_ENABLED=1 agentic photo --mock --json "前后对比拍照"
```

## 25. 实现顺序

按小步、可测试方式实现：

1. 定义 Agent App package 标准。
   - `config.json`
   - `entry.py`
   - `meta_requirements.txt`
   - `app.yaml`
   - `schemas/`
   - `policies/`
   - `prompts/`
   - `tests/`
2. 定义 Plan Schema / Policy Schema。
   - `schemas/photo_plan.schema.json`
   - `schemas/photo_result.schema.json`
   - `policies/robot_photographer.policy.yaml`
3. 定义 Agentic System Call Contract。
   - `perception.capture_photo`
   - `arm.move_named`
   - `robot.stop`
   - `robot.get_state`
   - `storage.list_recent_photos`
4. 实现 `perception.capture_photo` 纵向链路。
   - `CapturePhoto.srv`
   - bridge service
   - PNG + metadata + index
   - Runtime / SDK API
   - skill manifest
   - permission / resource lock / audit
5. 实现 AIOS Tool wrapper。
   - `agenticos/perception_capture_photo`
   - `agenticos/arm_move_named`
   - `agenticos/robot_stop`
   - `agenticos/robot_status`
   - `agenticos/recent_photos`
6. 实现 `RobotPhotographerAgent`。
   - `entry.py`
   - `planner.py`
   - `validation.py`
   - deterministic executor in `main.py`
7. 实现 `agentic photo` CLI。
8. 加 Runtime OpenAI-compatible LLM provider。
9. 加 LLM planner + rule fallback。
10. 加 evidence / audit / memory integration。
11. 真实机器人验收。
