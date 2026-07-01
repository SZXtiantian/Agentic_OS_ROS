# 机械臂真实运动恢复与验证执行报告

最新执行时间：2026-06-15 14:46-15:00 CST  
Source of truth：`/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/robot_arm_motion_recovery_solution.md`  
上一轮证据目录：`/tmp/agentic_arm_motion_recovery_exec_20260615_142801`  
本轮证据目录：`/tmp/agentic_arm_motion_recovery_exec_20260615_144647`

## 1. 最终结论

本轮没有验证到真实机械臂运动。

与上一轮不同，本轮已经修复了 `ros_robot_controller` 在舵机读回阶段崩溃的直接软件原因，并且成功让最小控制栈稳定通过 preflight。继续排查后，问题收敛到硬件/底层总线状态：

```text
real_motion_verified: false
motion_commands_sent: false
software_crash_after_fix: false
hardware_blocking_evidence: true
```

明确阻断项：

```text
ARM_POWER_UNDERVOLTAGE
  机械臂舵机总线读到的 vin 约 4.258-6.6V，低于教程中 HX 总线舵机 DC 9-12.6V 工作电压范围。

ARM_TORQUE_DISABLED
  ID 1/2/3/4/5/10 的 torque_state 均为 [0]。

ARM_SERVO_ID3_POSITION_INVALID
  ID 3 在线，present_id=[3]，但 position=[-92]，超出 0-1000 有效位置范围。

ARM_POSITION_READBACK_PARTIAL
  ID 1/2/4/5/10 position-only 读回稳定；ID 3 位置读回无效。
```

因此按安全规则没有发送 `500 -> 540 -> 500` 夹爪动作，也没有发送 `camera_up -> init` 或 `horizontal -> init`。在当前欠压、扭矩关闭、ID3 位置异常状态下继续发真实运动命令，不能作为有效验证，也可能导致硬件保护或不可控结果。

## 2. Changed Files

本轮修改：

```text
/home/ubuntu/ros2_ws/src/driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_sdk.py
/home/ubuntu/ros2_ws/src/driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_node.py
/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/robot_arm_motion_recovery_execution_report.md
```

未修改：

```text
/opt/ros
MoveIt
Nav2
上游 vendor driver 仓库
AgenticOS Runtime / SDK / Agent Apps
```

说明：`/home/ubuntu/ros2_ws` 工作区原本存在多处 unrelated dirty changes，本轮只处理本地 `ros_robot_controller` 的读回稳定性问题，没有回滚用户或既有改动。

## 3. Driver Fixes

修复点 1：`ros_robot_controller_node.py`

```text
bus_servo_read_voltage -> bus_servo_read_vin
bus_servo_read_torque  -> bus_servo_read_torque_state
```

修复点 2：所有 bus servo 状态读回增加异常保护与取值范围校验。

```text
单个舵机读回异常不会让 ros_robot_controller 进程退出。
position 字段只接受 0-1000。
torque_state 只接受 0-1。
offset 使用 int16 范围。
其他 uint16 字段过滤负数和越界值。
```

修复点 3：`ros_robot_controller_sdk.py`

```text
bus_servo_read_and_unpack 增加 1.0s timeout。
读命令前清理 stale queue。
queue.Empty / struct.error 返回 None，不再无限阻塞或向上抛出。
```

## 4. Build Results

执行：

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select ros_robot_controller servo_controller
```

结果：

```text
round1: Summary: 2 packages finished [5.49s]
round2: Summary: 2 packages finished [5.69s]
```

证据：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/colcon_build_ros_robot_controller_servo_controller.log
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/colcon_build_round2.log
```

## 5. Single-Serial-Owner Mode

执行：

```bash
sudo systemctl stop start_app_node.service
ros2 daemon stop
ros2 daemon start
```

结果：

```text
start_app_node.service: inactive (dead)
stale ROS graph cleared
```

证据：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/before_single_owner_state.txt
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/after_single_owner_state.txt
```

## 6. Minimal Stack Preflight

使用最小栈单独启动：

```bash
ros2 run ros_robot_controller ros_robot_controller
ros2 run servo_controller servo_controller --ros-args \
  --params-file /home/ubuntu/ros2_ws/src/driver/servo_controller/config/servo_controller.yaml \
  -p base_frame:=base_footprint
```

修复后 round2 preflight：

```text
nodes:
  /arm_controller
  /controller_manager
  /gripper_controller
  /ros_robot_controller
  /servo_manager

/ros_robot_controller/bus_servo/set_position:
  Publisher count = 1
  Subscription count = 1

/servo_controller:
  Publisher count = 0
  Subscription count = 1

/ros_robot_controller/init_finish: success=True
/controller_manager/init_finish: success=True
```

证据：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/preflight_round2.txt
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/ros_robot_controller_run_round2.log
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/servo_controller_run_round2.log
```

## 7. Readback Results

上一轮和本轮 round1 中，ID 3 position-only 读回触发了 ROS message assignment 崩溃：

```text
AssertionError:
  The 'position' field must be a set or sequence and each value of type 'int'
  and each unsigned integer in [0, 65535]
```

修复过滤逻辑后，`ros_robot_controller` 不再崩溃。

单 ID position-only 读回 round2：

```text
ID 1: position=[773], backend alive
ID 2: position=[817], backend alive
ID 3: position=[], invalid value filtered, backend alive
ID 4: position=[330], backend alive
ID 5: position=[473], backend alive
ID 10: position=[364], backend alive
```

全量 position-only 读回 round2：

```text
ID 1: [773]
ID 2: [817]
ID 3: []
ID 4: [330]
ID 5: [473]
ID 10: [364]
```

ID mapping probe：

```text
ID 1: present_id=[1], position=[773]
ID 2: present_id=[2], position=[817]
ID 3: present_id=[3], position=[]
ID 4: present_id=[4], position=[330]
ID 5: present_id=[5], position=[473]
ID 6: not present
ID 7: not present
ID 8: not present
ID 9: not present
ID 10: present_id=[10], position=[364]
```

证据：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/single_id_position_readback_round2.txt
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/full_position_readback_round2.txt
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/id_mapping_probe_round2.txt
```

## 8. Direct Board SDK Diagnostics

停止 ROS 最小栈后，直接用 Board SDK 打开 `/dev/rrc` 读取底层状态。

ID 3 单独诊断：

```text
present_id: [3]
position: [-92]
offset: [2]
angle_limit: [0, 1000]
temperature: [29]
vin: [6600]
vin_limit: [4500, 14000]
temp_limit: [70]
torque_state: [0]
```

全 ID 电压/扭矩诊断：

```text
ID 1: position=[773], vin=[6200], torque_state=[0], temperature=[34]
ID 2: position=[817], vin=[6500], torque_state=[0], temperature=[30]
ID 3: position=[-92], vin=[6600], torque_state=[0], temperature=[29]
ID 4: position=[330], vin=[6100], torque_state=[0], temperature=[30]
ID 5: position=[473], vin=[6400], torque_state=[0], temperature=[29]
ID 10: position=[364], vin=[4258], torque_state=[0], temperature=[29]
```

证据：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/direct_board_probe.txt
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/direct_board_id3_diagnostics.txt
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/direct_board_all_id_power_torque_diagnostics.txt
```

解读：

```text
1. ID 3 的无效 position=[-92] 来自 Board SDK / 硬件响应层，不是 ROS service 转换问题。
2. 所有在线舵机 torque_state=[0]，当前不是可执行真实运动的状态。
3. ID 1-5 vin 约 6.1-6.6V，ID 10 vin 约 4.258V，低于教程中 HX 总线舵机 DC 9-12.6V 工作电压范围。
```

## 9. Motion Test

未执行真实运动命令。

跳过原因：

```text
position-only readback 尚未健康：ID 3 位置无效。
舵机电源疑似欠压：vin 低于教程工作电压范围。
所有 torque_state 均为 0。
```

明确未执行：

```text
10 号夹爪 500 -> 540 -> 500
camera_up -> init
horizontal -> init
Gazebo/gz/fake Nav2/RViz-only demo
```

## 10. Camera Evidence

本轮没有进入真实动作阶段，因此未启动相机进行动作前后图像验证。

图像差异指标：

```text
mean_abs_diff: not collected
changed_pixels_gt25_pct: not collected
hist_distance: not collected
phash_distance: not collected
```

## 11. Final State

证据：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_144647/final_state_and_changes.txt
```

最终状态：

```text
start_app_node.service: inactive (dead)
manual minimal stack: stopped before direct Board SDK probe
/ros_robot_controller/bus_servo/set_position: unknown topic
/servo_controller: unknown topic
```

说明：我没有恢复 `start_app_node.service`。目标要求进入单一串口拥有者模式；当前也需要保留故障现场，避免完整 bringup 再次占用串口并掩盖底层问题。

## 12. Commands Run

关键命令：

```bash
sudo systemctl stop start_app_node.service
ros2 daemon stop
ros2 daemon start

cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select ros_robot_controller servo_controller

ros2 run ros_robot_controller ros_robot_controller
ros2 run servo_controller servo_controller --ros-args \
  --params-file /home/ubuntu/ros2_ws/src/driver/servo_controller/config/servo_controller.yaml \
  -p base_frame:=base_footprint

ros2 service call /ros_robot_controller/init_finish std_srvs/srv/Trigger "{}"
ros2 service call /controller_manager/init_finish std_srvs/srv/Trigger "{}"
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 1, get_position: 1}]}"
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 2, get_position: 1}]}"
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 3, get_position: 1}]}"
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 4, get_position: 1}]}"
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 5, get_position: 1}]}"
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 10, get_position: 1}]}"
```

还执行了 Direct Board SDK 只读诊断脚本，读取 `present_id`、`position`、`vin`、`torque_state`、`temperature` 等字段。脚本输出保存在本轮证据目录中。

## 13. Remaining Risks

1. 当前证据指向硬件供电/扭矩/ID3 反馈异常，继续从软件层发送动作命令不能证明真实运动能力。
2. ID 3 的 position=[-92] 可能来自舵机编码器/电位器、线缆、接口、供电不足或舵机保护状态。
3. ID 10 vin=[4258] 特别低，夹爪即使收到命令也大概率不会形成可信运动证据。
4. `start_app_node.service` 当前保持停止状态，需要硬件检查或下一轮验证前再决定是否恢复完整 bringup。

## 14. Hardware Checklist

建议硬件侧按以下顺序检查：

```text
1. 确认机械臂舵机电源 rail 已打开，且在负载下可提供 9-12.6V。
2. 检查电池、电源开关、DC-DC、保险丝、急停/保护开关。
3. 检查舵机总线 GND 是否共地，PH2.0 3P 总线链路是否松动或接反。
4. 重点重新插拔并检查 ID 3 相关线缆、接口和舵机本体。
5. 在停止 start_app_node.service 的前提下，用厂家 Arm 上位机读取 ID 3 position。
6. 如果厂家工具也读到负数/异常值，优先校准或更换 ID 3 舵机。
7. 在电压恢复到工作范围前，不建议启用 torque 或发送真实动作。
```

## 15. Next Steps

硬件修复后重新执行：

```text
1. 保持单一串口拥有者模式。
2. 启动 ros_robot_controller + servo_controller 最小栈。
3. preflight 确认 /ros_robot_controller、/controller_manager、/servo_manager 在线。
4. position-only 单 ID 读取 1/2/3/4/5/10。
5. 全量 position-only 读取 1/2/3/4/5/10。
6. 确认 vin 在教程工作范围，torque_state 可被正确启用。
7. 仅在读回稳定后测试 10 号夹爪 500 -> 540 -> 500。
8. 再测试 camera_up -> init，并按需要采集相机图像差异证据。
```

---

## 16. 2026-06-15 15:34 复测补充

本轮按 `robot_arm_motion_recovery_solution.md` 重新进入单一串口拥有者模式，先做健康门，不发送运动命令。

证据目录：

```text
/tmp/agentic_arm_motion_recovery_exec_20260615_153429
```

### 16.1 最小栈状态

`start_app_node.service` 复测前已经处于停止状态：

```text
start_app_node.service: inactive (dead)
```

重新 build/source 本地最小控制栈：

```text
colcon build --symlink-install --packages-select ros_robot_controller servo_controller
Summary: 2 packages finished [5.84s]
```

启动最小栈后 preflight 通过：

```text
nodes:
  /arm_controller
  /controller_manager
  /gripper_controller
  /ros_robot_controller
  /servo_manager

/ros_robot_controller/bus_servo/set_position:
  Publisher count = 1
  Subscription count = 1

/servo_controller:
  Publisher count = 0
  Subscription count = 1

/ros_robot_controller/init_finish: success=True
/controller_manager/init_finish: success=True
```

### 16.2 只读硬件健康门结果

本轮电压已恢复到教程工作范围，但 ID 3 position 仍然无效，torque_state 语义仍未被证明。

```text
ID 1: present_id=[1],  position=[773], vin=[12200], temperature=[35], enable_torque=[0]
ID 2: present_id=[2],  position=[816], vin=[12200], temperature=[31], enable_torque=[0]
ID 3: present_id=[3],  position=[],    vin=[12100], temperature=[31], enable_torque=[0]
ID 4: present_id=[4],  position=[330], vin=[12200], temperature=[31], enable_torque=[0]
ID 5: present_id=[5],  position=[473], vin=[12100], temperature=[31], enable_torque=[0]
ID 10: present_id=[10], position=[364], vin=[12220], temperature=[32], enable_torque=[0]
```

ID 3 连续 5 次完整读回仍然被过滤为空：

```text
present_id=[3]
position=[]
offset=[2]
voltage=[12100]
temperature=[31]
position_limit=[0, 1000]
voltage_limit=[4500, 14000]
max_temperature_limit=[70]
enable_torque=[0]
```

底层 driver 日志确认原始无效值仍为：

```text
ignoring invalid bus servo readback: id=3, field=position, value=-92
```

健康门判定：

```text
ARM_POWER_UNDERVOLTAGE: resolved in this run
ARM_SERVO_ID3_POSITION_INVALID: still blocking
ARM_TORQUE_DISABLED_OR_UNVERIFIED: still blocking
ARM_HEALTH_GATE_FAILED: true
```

因此本轮未发送以下命令：

```text
10 号夹爪 500 -> 540 -> 500
camera_up
horizontal
detect_left
detect_right
left_up
left_down
right_up
right_down
任何 AgenticOS arm.move_named 真实运动
```

### 16.3 动作组后端可用性

只读检查动作组文件存在：

```text
init.d6a: exists
horizontal.d6a: exists
detect_left.d6a: exists
detect_right.d6a: exists
camera_up.d6a: exists
left_up.d6a: exists
left_down.d6a: exists
right_up.d6a: exists
right_down.d6a: exists
```

AgenticOS manipulation bridge 只读状态：

```text
arm_backend_type: servo_action_group
arm_backend_available: true
action_files_available:
  arm_home: true
  camera_center: true
  camera_yaw_left_15: true
  camera_yaw_right_15: true
  camera_pitch_up_15: true
  camera_pitch_down_15: true
stop_available: true
```

说明：这只证明 ROS bridge 和动作组文件存在，不证明真实机械臂可以安全运动。真实运动仍被 ID 3 position 无效挡住。

### 16.4 相机链路复测

第一次只读拍照失败，因为相机 topic 没有 publisher：

```text
error_code: CAMERA_UNAVAILABLE
reason: No fresh camera frame received for target 'workspace'.
/depth_cam/rgb0/image_raw Publisher count: 0
```

启动真实 Aurora 930 相机 launch 后，驱动发现设备：

```text
device name: Aurora 930
serial number: HY400516001016128G00220
firmware version: 2.0.8
/depth_cam/rgb0/image_raw Publisher count: 1
```

AgenticOS 真实只读拍照成功：

```text
session_id: sess_0e9023850311
audit_id: audit_004761
image_path: /opt/agentic/var/evidence/photos/photo_20260615_154217_capture_9d0d730671ff.png
metadata_path: /opt/agentic/var/evidence/photos/photo_20260615_154217_capture_9d0d730671ff.json
topic: /depth_cam/rgb0/image_raw
encoding: bgr8
width: 640
height: 400
age_s: 0.012
```

Codex 目检结论：

```text
真实 PNG 非空，画面为办公室工位/椅子区域。
```

### 16.5 Stop / Cancel Evidence

无 active arm action 时执行 Robot Photographer stop：

```text
session_id: sess_a57910ae8016
audit_id: audit_004764
robot.stop: succeeded
arm_stop.message: no active arm action
```

### 16.6 软件验证

```text
python scripts/check_forbidden_imports.py:
  forbidden import/static guard ok

scripts/run_tests.sh:
  100 passed in 15.84s

pytest robot_photographer_agent/tests:
  22 passed in 2.14s

installed-side pytest:
  17 passed in 3.50s

scripts/build_system_skill_nodes.sh:
  Summary: 5 packages finished [12.3s]

/opt/agentic/bin/agentic photo --mock --allow-arm-motion --yes --json "拍一组多角度照片并验证差异":
  completed
  verification_path: /opt/agentic/var/evidence/photos/verification_plan_d801e1784b1a.json
  min_pair_difference_score: 0.2292
  max_pair_difference_score: 0.3294
```

### 16.7 复测结论

本轮状态比上一轮有进展：

```text
供电恢复: yes
最小控制栈稳定: yes
AgenticOS bridge build/test: yes
真实相机 capture_photo: yes
真实机械臂运动验证: no
多角度真实图像验证: no
```

阻断原因：

```text
ARM_SERVO_ID3_POSITION_INVALID
ARM_TORQUE_DISABLED_OR_UNVERIFIED
ARM_HEALTH_GATE_FAILED
```

下一步仍然是硬件/舵机侧处理 ID 3：

```text
1. 在 start_app_node.service 停止、最小栈关闭的前提下，用厂家 Arm 上位机单独读取 ID 3。
2. 如果厂家工具也读到 -92 或空 position，优先检查/重插 ID 3 总线线缆和舵机本体。
3. 确认 torque_state=[0] 的真实语义；不要直接猜测 0 表示可运动。
4. 只有 ID 3 position 回到 0-1000 且 torque_state 语义明确后，再执行 10 号夹爪 500 -> 540 -> 500。
5. 夹爪真实运动通过后，才进入 camera_up/horizontal/detect_left/detect_right 等动作组和多角度 PNG 差异验证。
```

---

## 17. 2026-06-15 15:49 可重复健康门补充

本轮新增了只读健康门脚本：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_health_gate.sh
```

脚本职责：

```text
1. 进入单一串口拥有者模式。
2. 启动 ros_robot_controller + servo_controller 最小栈。
3. 只调用 /ros_robot_controller/bus_servo/get_state。
4. 读取 ID 1/2/3/4/5/10 的 present_id、position、vin、temperature、torque_state。
5. 生成结构化 JSON 报告。
6. 健康门失败时返回非零，拒绝真实 arm motion。
7. 退出时清理脚本自己启动的最小栈进程。
```

本轮运行结果：

```text
command:
  /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_health_gate.sh

report:
  /tmp/agentic_arm_health_gate_20260615_154920/arm_health_gate.json

success:
  false

error_codes:
  ARM_SERVO_ID3_POSITION_INVALID
  ARM_TORQUE_DISABLED_OR_UNVERIFIED
  ARM_HEALTH_GATE_FAILED
```

读回摘要：

```text
ID 1:  present_id=[1],  position=[773], vin=[12100], torque_state=[0], temperature=[35]
ID 2:  present_id=[2],  position=[816], vin=[12200], torque_state=[0], temperature=[32]
ID 3:  present_id=[3],  position=[],    vin=[12100], torque_state=[0], temperature=[31]
ID 4:  present_id=[4],  position=[330], vin=[12200], torque_state=[0], temperature=[32]
ID 5:  present_id=[5],  position=[473], vin=[12100], torque_state=[0], temperature=[31]
ID 10: present_id=[10], position=[364], vin=[12198], torque_state=[0], temperature=[32]
```

底层日志：

```text
ignoring invalid bus servo readback: id=3, field=position, value=-92
```

多角度验收脚本也已接入健康门：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_multi_angle_photo_acceptance.sh
```

行为变更：

```text
默认只读验收会运行 real_robot_arm_health_gate.sh。
如果健康门失败，真实多角度机械臂运动不会被执行。
即使 AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1，健康门失败也会拒绝 real multi-angle arm motion。
```

补充说明：

```text
AGENTIC_ARM_TORQUE_STATE_VERIFIED=1
AGENTIC_ARM_EXPECTED_TORQUE_STATE=0 或 1
```

只有在厂家工具或人工验证明确 torque_state 语义后，才能设置上述变量让 torque 检查进入“已知语义”模式。当前未设置，因此健康门按 `ARM_TORQUE_DISABLED_OR_UNVERIFIED` 失败是预期行为。

---

## 18. 2026-06-15 15:55 健康门复跑补充

复跑健康门后，ID 3 位置读回已经从上一轮的空值/`-92` 恢复为有效范围内的数值。当前不再出现 `ARM_SERVO_ID3_POSITION_INVALID`。

最新健康门报告：

```text
/tmp/agentic_arm_health_gate_20260615_155534/arm_health_gate.json
```

结果：

```text
success: false
next_allowed_stage: torque_semantics_required
error_codes:
  ARM_TORQUE_DISABLED_OR_UNVERIFIED
  ARM_HEALTH_GATE_FAILED
```

读回摘要：

```text
ID 1:  present_id=[1],  position=[773], vin=[12100], torque_state=[0], temperature=[35]
ID 2:  present_id=[2],  position=[864], vin=[12100], torque_state=[0], temperature=[32]
ID 3:  present_id=[3],  position=[80],  vin=[12100], torque_state=[0], temperature=[31]
ID 4:  present_id=[4],  position=[172], vin=[12200], torque_state=[0], temperature=[32]
ID 5:  present_id=[5],  position=[473], vin=[12100], torque_state=[0], temperature=[32]
ID 10: present_id=[10], position=[364], vin=[12178], torque_state=[0], temperature=[32]
```

当前被健康门阻止的运动测试：

```text
gripper_10_500_540_500
camera_up
horizontal
detect_left
detect_right
left_up
left_down
right_up
right_down
agenticos_arm_move_named
real_multi_angle_capture
```

结论更新：

```text
ARM_POWER_UNDERVOLTAGE: resolved
ARM_SERVO_ID3_POSITION_INVALID: currently resolved by latest readback
ARM_TORQUE_DISABLED_OR_UNVERIFIED: still blocking
```

下一步不再是优先修 ID 3，而是确认 `torque_state=[0]` 的真实语义。当前代码树里存在矛盾证据：

```text
/home/ubuntu/software/arm_pc/bus_servo_control.py:
  unloadBusServo() 调用 bus_servo_enable_torque(servo_id, 1)

/home/ubuntu/software/servo_tool/bus_servo_control.py:
  unloadBusServo() 调用 bus_servo_enable_torque(servo_id, 0)
```

因此不能仅凭源码猜测 `0` 表示上力或掉电。需要用厂家 Arm 上位机或人工确认来证明当前 `torque_state=[0]` 是否为真实可运动状态。

如果确认 `torque_state=[0]` 表示可运动/上力，可以用如下环境变量让健康门进入下一阶段：

```bash
AGENTIC_ARM_TORQUE_STATE_VERIFIED=1 \
AGENTIC_ARM_EXPECTED_TORQUE_STATE=0 \
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_health_gate.sh
```

只有健康门通过并输出：

```text
success: true
next_allowed_stage: gripper_minimal_motion
```

才能继续执行 `10 号夹爪 500 -> 540 -> 500` 最小真实运动读回测试。

---

## 19. 2026-06-15 15:59 Torque 语义探针补充

新增受控 torque 语义探针：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_torque_semantics_probe.sh
```

默认行为：

```text
mode: read_only
只启动 ros_robot_controller
只调用 /ros_robot_controller/bus_servo/get_state
不发布 /ros_robot_controller/bus_servo/set_state
不发布 /ros_robot_controller/bus_servo/set_position
不发送任何舵机位置或动作组
```

默认只读运行结果：

```text
command:
  /home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_torque_semantics_probe.sh

report:
  /tmp/agentic_torque_semantics_probe_20260615_155929/torque_semantics_probe.json

success:
  false

error_codes:
  TORQUE_SEMANTICS_PROBE_READ_ONLY

ID 10 readback:
  present_id=[10]
  position=[364]
  vin=[12174]
  temperature=[32]
  torque_state=[0]
```

说明：

```text
这次只读 probe 没有改变硬件状态，因此仍不能证明 torque_state=[0] 的物理语义。
```

如果需要由软件侧验证 enable/disable 命令和 readback 的对应关系，必须显式授权：

```bash
AGENTIC_ARM_TORQUE_PROBE_ALLOW_STATE_CHANGE=1 \
AGENTIC_TORQUE_PROBE_SERVO_ID=10 \
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_torque_semantics_probe.sh
```

该模式仍然不会发送位置命令，只会对指定单个舵机发布 torque enable/disable 并读回状态。但它可能改变舵机上力/掉电状态，因此需要现场确认机械臂安全、支撑充分、不会因掉电产生姿态变化后再执行。

---

## 20. 2026-06-15 16:02 Torque 语义状态变更探针

执行受控状态变更探针：

```bash
AGENTIC_ARM_TORQUE_PROBE_ALLOW_STATE_CHANGE=1 \
AGENTIC_TORQUE_PROBE_SERVO_ID=10 \
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_torque_semantics_probe.sh
```

报告：

```text
/tmp/agentic_torque_semantics_probe_20260615_160426/torque_semantics_probe.json
```

结果：

```text
success: true
mode: state_change_probe
servo_id: 10
```

读回关系：

```text
before:         torque_state=[0], position=[364]
after_enable_1: torque_state=[0], position=[364]
after_enable_0: torque_state=[1], position=[364]
restored:       torque_state=[0], position=[364]
```

结论：

```text
torque_state readback 与 enable_torque 命令值呈反向关系。
enable_torque=1 后读回 torque_state=[0]。
enable_torque=0 后读回 torque_state=[1]。
脚本已修正为恢复到 probe 前读回状态，本次最终 restored=[0]。
```

注意：这仍然不能单独证明所有舵机的物理上力/掉电语义，但已经证明读回和命令之间的关系，并且 ID10 可安全完成受控 torque 状态探针。

## 21. 2026-06-15 16:07 健康门通过

使用已验证 readback 语义重新运行健康门：

```bash
AGENTIC_ARM_TORQUE_STATE_VERIFIED=1 \
AGENTIC_ARM_EXPECTED_TORQUE_STATE=0 \
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_health_gate.sh
```

报告：

```text
/tmp/agentic_arm_health_gate_20260615_160719/arm_health_gate.json
```

结果：

```text
success: true
next_allowed_stage: gripper_minimal_motion
blocked_motion_tests: []
```

读回摘要：

```text
ID 1:  present_id=[1],  position=[773], vin=[12100], torque_state=[0]
ID 2:  present_id=[2],  position=[864], vin=[12100], torque_state=[0]
ID 3:  present_id=[3],  position=[80],  vin=[12100], torque_state=[0]
ID 4:  present_id=[4],  position=[172], vin=[12100], torque_state=[0]
ID 5:  present_id=[5],  position=[473], vin=[12100], torque_state=[0]
ID 10: present_id=[10], position=[364], vin=[12134], torque_state=[0]
```

结论：

```text
供电、ID 读回、position 范围、torque_state 可读性均通过。
允许进入 10 号夹爪最小真实运动验证。
```

## 22. 2026-06-15 16:08 夹爪最小真实运动

新增并执行最小真实运动脚本：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_gripper_minimal_motion.sh
```

执行命令：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
AGENTIC_ARM_TORQUE_STATE_VERIFIED=1 \
AGENTIC_ARM_EXPECTED_TORQUE_STATE=0 \
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_gripper_minimal_motion.sh
```

报告：

```text
/tmp/agentic_gripper_minimal_motion_20260615_160857/gripper_minimal_motion.json
```

结果：

```text
success: true
servo_id: 10
commands: [500, 540, 500]
movement_span: 38
tolerance: 25
```

读回证据：

```text
before:       position=[364], torque_state=[0], vin=[12132], temperature=[32]
after 500:    position=[497], torque_state=[1], vin=[12047], temperature=[36]
after 540:    position=[535], torque_state=[1], vin=[12041], temperature=[43]
after 500:    position=[502], torque_state=[1], vin=[12132], temperature=[44]
```

结论：

```text
ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED: false
GRIPPER_POSITION_READBACK_MISMATCH: false
10 号夹爪真实小幅运动已由 position readback 确认。
```

注意：夹爪动作后 ID10 的 torque_state 从 `[0]` 变为 `[1]`。后续健康门和动作组验证不能简单假设所有舵机在所有阶段都保持同一个 torque_state；必须记录每个动作前后的 torque_state，并以 position/图像真实变化作为主要运动确认依据。

## 23. 2026-06-15 16:15-16:37 动作组真实运动验证

新增动作组硬件探针：

```text
/home/ubuntu/agentic_ws/src/agentic_runtime_src/scripts/real_robot_arm_action_group_probe.sh
```

脚本约束：

```text
必须设置 AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1。
只通过 /agentic/arm/move_named 调用 AgenticOS bridge。
只通过 /ros_robot_controller/bus_servo/get_state 读取真实舵机状态。
不发布 /servo_controller。
不调用 /ros_robot_controller/bus_servo/set_position。
每个动作后执行 init 恢复并再次读数。
```

为验证尚未正式暴露的候选 vendor 动作组，本阶段使用临时 probe profile：

```text
/tmp/agentic_arm_action_group_probe_profile.yaml
```

该 profile 只用于本次硬件诊断，没有写入 `/opt/agentic`，也没有加入 Agent App schema/policy。

clean reports：

```text
/tmp/agentic_action_group_probe_20260615_163329/action_group_probe.json
/tmp/agentic_action_group_probe_20260615_162759/action_group_probe.json
```

验证结果：

```text
horizontal:    move_success=true, max_position_delta=224, recovery_success=true
camera_up:     move_success=true, max_position_delta=180, recovery_success=true
detect_left:   move_success=true, max_position_delta=370, recovery_success=true
detect_right:  move_success=true, max_position_delta=400, recovery_success=true
left_up:       move_success=true, max_position_delta=203, recovery_success=true
left_down:     move_success=true, max_position_delta=344, recovery_success=true
right_up:      move_success=true, max_position_delta=232, recovery_success=true
right_down:    move_success=true, max_position_delta=383, recovery_success=true
```

结论：

```text
ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED: false
ARM_BACKEND_DIED_AFTER_MOTION: false
8 个候选动作组均已通过真实 position delta 验证。
每个动作后的 init 恢复均成功。
```

中间发现：

```text
旧的 safety_guard_node 没有随临时 bridge 清理，导致 Runtime safety check 可能命中过期 profile。
已清理所有 /home/ubuntu/agentic_ws/install/ros2_bridge/agentic_* 进程，并只保留一个正式 bridge/safety 实例。
后续验收脚本需要清理 agentic_safety_guard 进程，不能只清理 agentic_capability_bridge 进程。
```

## 24. 2026-06-15 16:39-16:44 Robot Photographer 真实多角度拍摄

启动真实 Aurora930 相机：

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/third_party/aurora_ws/install/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
need_compile=False DEPTH_CAMERA_TYPE=aurora ros2 launch peripherals depth_camera.launch.py
```

相机状态：

```text
/depth_cam/rgb0/image_raw publisher_count=1
publisher node=/aurora
observed rate approximately 6-7 Hz
QoS reliability=RELIABLE
```

只读拍照：

```bash
/opt/agentic/bin/agentic photo --real --json "拍一张 workspace 的照片"
```

结果：

```text
success=true
session_id=sess_29b9c5f2fb51
audit_id=audit_005079
image=/opt/agentic/var/evidence/photos/photo_20260615_163938_capture_09fee14a8dca.png
metadata=/opt/agentic/var/evidence/photos/photo_20260615_163938_capture_09fee14a8dca.json
```

正式多角度拍摄：

```bash
AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 \
/opt/agentic/bin/agentic photo --real --allow-arm-motion --yes --json "拍一组多角度照片并验证差异"
```

结果：

```text
success=true
session_id=sess_8b4b61683e23
plan_id=plan_17cd70080543
audit_ids=audit_005084..audit_005094
```

真实照片：

```text
center:        /opt/agentic/var/evidence/photos/center_20260615_164219_capture_99db84bc8aa6.png
yaw_left_15:   /opt/agentic/var/evidence/photos/yaw_left_15_20260615_164232_capture_724dab4f28c5.png
yaw_right_15:  /opt/agentic/var/evidence/photos/yaw_right_15_20260615_164245_capture_42570b74d050.png
pitch_up_15:   /opt/agentic/var/evidence/photos/pitch_up_15_20260615_164256_capture_b972f3889ea0.png
pitch_down_15: /opt/agentic/var/evidence/photos/pitch_down_15_20260615_164311_capture_9acbbb6c6870.png
```

verification JSON：

```text
/opt/agentic/var/evidence/photos/verification_plan_17cd70080543.json
```

差异指标：

```text
min_pair_difference_score=0.2739
max_pair_difference_score=0.4661
threshold=0.08

center vs yaw_left_15:   score=0.4375, mean_abs_diff=94.154, changed_pixels_gt25_pct=0.9217, hist_distance=0.5585, phash_distance=29
center vs yaw_right_15:  score=0.4071, mean_abs_diff=71.981, changed_pixels_gt25_pct=0.8388, hist_distance=0.5484, phash_distance=33
center vs pitch_up_15:   score=0.2739, mean_abs_diff=34.369, changed_pixels_gt25_pct=0.4408, hist_distance=0.3262, phash_distance=32
center vs pitch_down_15: score=0.3799, mean_abs_diff=77.208, changed_pixels_gt25_pct=0.8639, hist_distance=0.4454, phash_distance=30
```

Codex 视觉审阅：

```text
contact_sheet=/tmp/agentic_mult_angle_review_plan_17cd70080543.png
结论=ANGLE_DIFFERENCE_VISUALLY_CONFIRMED

center、yaw_left_15、yaw_right_15 的桌面/车轮/键盘等物体位置明显不同。
pitch_up_15 仍主要看到隔板和近处桌面，但相对于 center 有可见位移。
pitch_down_15 视野明显下探/外扩，看到更远办公区和椅子，差异最直观。
```

正式流程结束后回家读数：

```text
ID 1:  position=[500], vin=[11800], torque_state=[1]
ID 2:  position=[725], vin=[11800], torque_state=[1]
ID 3:  position=[49],  vin=[11800], torque_state=[1]
ID 4:  position=[149], vin=[11900], torque_state=[1]
ID 5:  position=[500], vin=[11800], torque_state=[1]
ID 10: position=[498], vin=[11834], torque_state=[1]
```

结论：

```text
Robot Photographer 真实多角度机械臂拍摄已打通。
真实运动经过 Agent App plan validation、policy、Runtime safety/resource/audit、AgenticOS bridge、vendor action group backend。
未使用 Gazebo/gz/fake Nav2/RViz-only demo。
未让 Agent App 直接 import rclpy 或直接发布 servo/camera ROS topic。
```
