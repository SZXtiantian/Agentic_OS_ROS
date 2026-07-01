# Robot Photographer 多角度机械臂拍摄计划

本文档是对 `robot_photographer_agent` 的增量实现计划。目标是在现有 AIOS-compatible + AgenticOS-safe Robot Photographer 基础上，加入可控的机械臂相机角度调整能力，并验证不同角度拍到的图片确实不同。

本计划不推翻现有架构。仍以 `/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/robot_photographer_agent_technical_design.md` 和现有 `robot_photographer_agent` 实现为 source of truth。

## 1. 目标

Robot Photographer 需要从“单角度拍照”升级为“受控多角度拍摄”：

- 用户可以用自然语言要求机器人从多个相机角度拍摄工作区。
- 机械臂通过离散、安全、可审计的 named camera pose 调整相机角度。
- 支持水平旋转、向上俯仰、回中、回初始位。
- 向下俯仰当前不开放；`camera_pitch_down_15` 不能映射到 `left_down.d6a` 或任何未验证后端。
- 每个角度拍摄真实 PNG 和 metadata。
- 每次机械臂动作都经过 AgenticOS Runtime/Kernel 的权限、安全、资源锁、timeout、bridge allowlist 和 audit。
- 拍摄结束后，Codex/验收脚本要验证不同角度的图片确实存在可量化差异。

## 2. 不可破坏边界

继续保持现有真实机器人边界：

- Agent App / Runtime / SDK 不能 import `rclpy`。
- Agent App 不能直接订阅 camera topic。
- Agent App 不能直接发布 servo topic。
- Agent App 不能直接调用 MoveIt、Nav2、kinematics、`/cmd_vel`、`/scan`、`/odom` 或 `/tf`。
- 只有 ROS2 bridge packages 可以 import `rclpy`。
- LLM / VLM 不能执行实时闭环控制。
- 不允许 LLM 输出任意关节目标、任意 servo pulse、笛卡尔轨迹、自由抓取、底盘移动。
- 不能修改 `/opt/ros`、MoveIt、Nav2 或 vendor drivers。
- 不添加 Gazebo、gz、fake Nav2、RViz-only demo 或 fake success。

机械臂角度调整必须表达为 AgenticOS allowlist 中的 named action / named camera pose。

## 3. 产品形态

推荐自然语言：

```text
从不同角度拍几张工作区
左右各拍一张
从中间、左边、右边、上面拍照
先回中间，然后左转、右转、抬高分别拍照
拍一组多角度照片，并确认这些照片确实不一样
```

推荐 CLI：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
/opt/agentic/bin/agentic --real --allow-arm-motion --yes "拍一组多角度照片并验证差异"
```

只做计划不动机械臂：

```bash
/opt/agentic/bin/agentic --mock --json "拍一组多角度照片并验证差异"
```

## 4. 多角度动作命名

### 4.1 新增 camera pose allowlist

建议新增一组离散 named camera pose：

```text
camera_center
camera_yaw_left_15
camera_yaw_right_15
camera_pitch_up_15
arm_home
```

可选扩展：

```text
camera_yaw_left_30
camera_yaw_right_30
camera_pitch_up_25
```

命名原则：

- `camera_*` 表示相机姿态，不表示任意机械臂控制。
- 数字只表示业务语义上的目标角度档位，不允许 App 直接发送角度值。
- 实际后端可以是 vendor action group、校准文件、或 bridge 内部安全映射。
- 如果对应后端文件或服务不存在，必须返回结构化错误，不能假成功。

### 4.2 必须先发现真实后端

实现前先检查：

- `/home/ubuntu/software/arm_pc/ActionGroups`
- 当前已有 `init.d6a`、`camera_up.d6a`
- 是否存在 left/right/up/down/center 相关 action group 文件
- `servo_controller` 是否在线
- `manipulation_bridge_node` 是否能 stop/cancel active action

如果没有对应 action group 文件：

- 不直接创建任意 servo pulse 动作。
- 不让 Agent App 计算关节角。
- 先生成 `CAMERA_POSE_BACKEND_MISSING` 或 `ARM_ACTION_BACKEND_MISSING`。
- 后续可以通过人工示教/厂商工具生成动作组，再由 AgenticOS robot profile 引用。

## 5. Bridge Profile 设计

在 `/opt/agentic/etc/robot_profiles/rosorin_arm_camera.yaml` 的 `arm.allowed_named_actions` 扩展：

```yaml
arm:
  allowed_named_actions:
    arm_home:
      backend: servo_action_group
      backend_action: init
      duration_s: 5
    camera_center:
      backend: servo_action_group
      backend_action: camera_center
      duration_s: 5
    camera_yaw_left_15:
      backend: servo_action_group
      backend_action: camera_yaw_left_15
      duration_s: 5
    camera_yaw_right_15:
      backend: servo_action_group
      backend_action: camera_yaw_right_15
      duration_s: 5
    camera_pitch_up_15:
      backend: servo_action_group
      backend_action: camera_pitch_up_15
      duration_s: 5
```

`camera_pitch_down_15` 必须保持未映射，直到完成独立后端动作验证。

要求：

- bridge 启动时记录每个 named action 对应的 backend 是否存在。
- `arm.get_state()` 返回 `camera_pose_actions_available`。
- `arm.move_named()` 对不存在的动作返回 `ARM_ACTION_BACKEND_MISSING`。
- 每个动作 timeout 必须 `<= 8s`。
- stop/cancel 必须继续可用；缺失时返回明确的 `ARM_STOP_BACKEND_MISSING`。

## 6. App Manifest / Policy 更新

### 6.1 `app.yaml`

扩展 allowed arm actions：

```yaml
allowed_arm_actions:
  - arm_home
  - camera_center
  - camera_yaw_left_15
  - camera_yaw_right_15
  - camera_pitch_up_15
```

新增资源声明：

```yaml
resources:
  - camera
  - arm
  - photo_verifier
```

### 6.2 `policies/robot_photographer.policy.yaml`

扩展 allowlist：

```yaml
motion:
  allowed_named_actions:
    - arm_home
    - camera_center
    - camera_yaw_left_15
    - camera_yaw_right_15
    - camera_pitch_up_15
  arm_action_timeout_s_max: 8

multi_angle:
  max_pose_count: 4
  require_return_home_after_sequence: true
  require_difference_verification: true
  min_image_difference_score: 0.08
```

仍然禁止：

```yaml
disallowed:
  arbitrary_joint_targets: true
  cartesian_trajectories: true
  freeform_grasping: true
  base_motion: true
  direct_servo_pulses_from_app: true
```

## 7. Plan Schema 更新

### 7.1 新 intent

新增：

```text
multi_angle_capture
verify_photo_differences
```

保留现有 intent：

```text
capture_photo
capture_burst
move_camera_pose
arm_home
before_after_capture
recent_photos
status
stop
unsupported
```

### 7.2 新 step type

新增 deterministic step：

```text
verify_photo_differences
```

允许 step：

```text
capture_photo
arm_named_action
recent_photos
status
stop
sleep
verify_photo_differences
```

示例 plan：

```json
{
  "schema_version": "1.0",
  "plan_id": "plan_multi_angle_example",
  "intent": "multi_angle_capture",
  "risk_class": "named_motion",
  "requires_motion": true,
  "needs_confirmation": true,
  "planner_mode": "llm",
  "target": "workspace",
  "steps": [
    {"type": "arm_named_action", "name": "camera_center", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "center", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_yaw_left_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "yaw_left_15", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_yaw_right_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "yaw_right_15", "timeout_s": 5},
    {"type": "arm_named_action", "name": "camera_pitch_up_15", "timeout_s": 8},
    {"type": "capture_photo", "target": "workspace", "label": "pitch_up_15", "timeout_s": 5},
    {
      "type": "verify_photo_differences",
      "method": "perceptual_hash_and_ssim",
      "min_difference_score": 0.08
    },
    {"type": "arm_named_action", "name": "arm_home", "timeout_s": 8}
  ],
  "user_summary": "从中心、左右、上方多个角度拍摄工作区并验证差异"
}
```

## 8. Planner 更新

### 8.1 Rule fallback

规则识别：

- `多角度`、`不同角度`、`一组角度` -> `multi_angle_capture`
- `左右`、`左边右边` -> `camera_yaw_left_15` + `camera_yaw_right_15`
- `上面`、`抬高`、`pitch up` -> `camera_pitch_up_15`
- `向下`、`降低`、`pitch down` -> `unsupported`
- `回中间` -> `camera_center`
- `验证不一样`、`确认不同` -> 添加 `verify_photo_differences`

### 8.2 LLM planner

LLM 仍只输出 bounded JSON plan。

新增 prompt 约束：

- 只能使用 allowlist camera pose。
- 不允许输出 angle 数值作为控制参数。
- 不允许输出 joint、servo、trajectory、pose target。
- 多角度计划最多 4 个拍摄姿态。
- 如果用户要求“验证是否不一样”，必须加入 `verify_photo_differences` step。
- motion plan 必须 `requires_motion=true`、`needs_confirmation=true`。

## 9. Deterministic Executor 更新

`main.py` 增加：

```text
verify_photo_differences
```

executor 行为：

1. 收集当前 plan 中所有成功的 `capture_photo` step。
2. 读取每张照片的 PNG 文件。
3. 使用确定性算法计算差异。
4. 写入 verification JSON。
5. 返回结构化结果。

executor 仍禁止：

- 调 LLM。
- 解析原始自然语言。
- 直接调用 ROS。
- 直接控制机械臂。

## 10. 图片差异验证设计

### 10.1 目标

验证多角度照片满足：

- 文件存在。
- metadata 中 topic、尺寸、时间戳有效。
- 图片不是空文件。
- 不同角度的图像内容存在可量化差异。
- 差异超过阈值时返回 `success=true`。
- 差异不足时返回 `PHOTO_DIFFERENCE_TOO_SMALL`，不能假成功。

### 10.2 建议算法

使用轻量 OpenCV / numpy：

1. 读取图片，统一 resize 到固定尺寸，例如 `320x200`。
2. 转灰度。
3. 计算平均绝对像素差 `mean_abs_diff`。
4. 计算直方图差异 `hist_distance`。
5. 计算感知 hash 汉明距离 `phash_distance`。
6. 可选计算 ORB feature match ratio。
7. 汇总为 `difference_score`。

建议初始判定：

```text
difference_score >= 0.08
```

或：

```text
mean_abs_diff >= 8.0
phash_distance >= 6
```

### 10.3 结构化输出

verification JSON 保存到：

```text
/opt/agentic/var/evidence/photos/verification_<plan_id>.json
```

示例：

```json
{
  "schema_version": "1.0",
  "plan_id": "plan_multi_angle_example",
  "success": true,
  "method": "perceptual_hash_and_ssim",
  "min_difference_score": 0.08,
  "pairs": [
    {
      "a_label": "center",
      "b_label": "yaw_left_15",
      "mean_abs_diff": 14.2,
      "hist_distance": 0.19,
      "phash_distance": 12,
      "difference_score": 0.21,
      "different": true
    }
  ],
  "error_code": "",
  "reason": ""
}
```

错误码：

```text
PHOTO_VERIFICATION_NO_IMAGES
PHOTO_VERIFICATION_IMAGE_MISSING
PHOTO_VERIFICATION_READ_FAILED
PHOTO_DIFFERENCE_TOO_SMALL
PHOTO_VERIFICATION_BACKEND_INCOMPLETE
```

## 11. Codex 验证要求

实现完成后，Codex 需要做两层验证：

### 11.1 程序化验证

运行：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
/opt/agentic/bin/agentic --real --allow-arm-motion --yes --json "拍一组多角度照片并验证差异"
```

检查：

- 每个 angle label 都有 PNG。
- 每个 PNG 有 metadata。
- verification JSON 存在。
- `difference_score` 超过阈值。
- 如果分数不足，报告 `PHOTO_DIFFERENCE_TOO_SMALL`。

### 11.2 Codex 人工审阅

Codex 需要打开或抽样查看图片，确认：

- 中心、左、右、上照片视角确实不同。
- 图像内容不是重复文件。
- metadata 的 timestamp 不同。
- index.jsonl 包含对应 entries。

如果视觉上不明显不同，不能说成功，需要给出：

```text
ANGLE_DIFFERENCE_NOT_VISUALLY_CONFIRMED
```

并建议重新校准 action group 或增大离散角度。

## 12. Acceptance Script 更新

新增：

```text
real_robot_multi_angle_photo_acceptance.sh
```

默认只读：

- 检查 profile。
- 检查 action group 文件或 backend availability。
- 检查 `/agentic/arm/get_state`。
- 检查 `/agentic/perception/capture_photo`。
- 不移动机械臂。

只有满足以下条件才执行真实多角度动作：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1
```

并要求命令传入：

```bash
--allow-arm-motion --yes
```

验收命令：

```bash
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_multi_angle_photo_acceptance.sh
```

运动验收：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_multi_angle_photo_acceptance.sh
```

## 13. 测试要求

新增或更新：

- schema accepts `multi_angle_capture`。
- schema accepts `verify_photo_differences` step。
- policy rejects non-allowlisted camera pose。
- policy rejects arbitrary angle / joint / servo fields。
- planner maps “左右拍照” to yaw-left/yaw-right named actions。
- planner maps “上面拍照” to `camera_pitch_up_15`。
- planner rejects “向下/降低/pitch down” with structured unsupported output。
- LLM output with raw angle numbers is rejected。
- motion still requires env/flag/confirmation。
- executor runs `verify_photo_differences` only after capture steps。
- verifier detects duplicate images as `PHOTO_DIFFERENCE_TOO_SMALL`。
- verifier accepts intentionally different fixture images。
- no-rclpy / no direct ROS guard still passes。
- robot profile missing action group returns structured backend missing error。
- real robot acceptance read-only default does not move arm。

## 14. 实现顺序

1. 真实 ROS graph 和 action group discovery。
2. 确定可用 camera pose named actions。
3. 更新 robot profile allowlist。
4. 更新 `app.yaml` 和 policy allowlist。
5. 更新 `photo_plan.schema.json`。
6. 更新 prompt 和 planner rule fallback。
7. 更新 validator policy checks。
8. 更新 deterministic executor，加入 `verify_photo_differences`。
9. 新增 photo verifier 模块。
10. 新增 CLI/acceptance script。
11. 跑 mock tests。
12. 跑 installed-side tests。
13. 跑真实只读验收。
14. 在 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1` 下跑真实多角度拍摄。
15. Codex 程序化 + 人工审阅图片差异。

## 15. 完成标准

完成时必须输出：

- changed files。
- 新增 camera pose allowlist。
- 真实 robot profile 中每个 named pose 的 backend availability。
- commands run。
- test results。
- real robot multi-angle photos paths。
- verification JSON path。
- difference scores。
- Codex 视觉审阅结论。
- remaining risks。
- next steps。

不能把硬件缺失、动作组缺失、图像差异不足报告为成功。
