# 机械臂“动作完成但实物不动”解决方案

本文基于以下材料整理：

- 教程：`/home/ubuntu/8.机械臂运动控制.pdf`
- 当前实机测试证据：`/tmp/agentic_arm_camera_motion_test_20260615_122005`
- 恢复执行报告：`/home/ubuntu/agentic_ws/src/agentic_runtime_src/docs/robot_arm_motion_recovery_execution_report.md`
- 恢复执行证据：`/tmp/agentic_arm_motion_recovery_exec_20260615_142801`
- 最新恢复执行证据：`/tmp/agentic_arm_motion_recovery_exec_20260615_144647`
- 当前 ROS2 工作区：`/home/ubuntu/ros2_ws`
- AgenticOS 约束：Agent App / Runtime / SDK 不直接控制 ROS topic/service；机器人运动最终必须走 Runtime 权限、安全、资源锁、审计和 bridge/HAL。

## 1. 结论摘要

当前问题不是“动作组没有发布”，而是“动作组发布成功后，不能证明真实舵机执行成功”。

已经观察到：

1. `/servo_controller` 可以收到动作组命令。
2. `/controller_manager/servo_states` 会显示目标位置变化。
3. 但相机画面在 `horizontal -> init` 大动作后几乎不变：

   ```text
   after_restart_before_vs_after_restart_horizontal:
     mean_abs_diff ~= 1.34
     changed_pixels_gt25_pct = 0%

   after_restart_before_vs_after_restart_init:
     mean_abs_diff ~= 1.37
     changed_pixels_gt25_pct = 0%
   ```

4. `ros_robot_controller` 曾经从 `start_app_node.service` 内崩溃退出，导致 `/ros_robot_controller/bus_servo/set_position` 没有订阅者，真实硬件后端断开。
5. systemd 日志里出现明确错误：

   ```text
   AttributeError: 'Board' object has no attribute 'bus_servo_read_voltage'
   ```

因此，后续不能再把 `/controller_manager/servo_states` 或“动作完成”作为真实运动成功的依据。必须用硬件后端在线状态 + position-only 舵机读回 + 图像变化证据共同判断。

## 1.1 最新执行报告补充结论

根据 `robot_arm_motion_recovery_execution_report.md`，上一轮已经把问题从“读回导致 driver 崩溃”推进到了“硬件/底层总线状态阻断真实运动”。

关键结果：

```text
real_motion_verified: false
motion_commands_sent: false
software_crash_after_fix: false
hardware_blocking_evidence: true
```

本地 ROS2 driver source 已经完成两类修复：

```text
ros_robot_controller_node.py:
  bus_servo_read_voltage -> bus_servo_read_vin
  bus_servo_read_torque  -> bus_servo_read_torque_state
  bus_servo 状态读回增加异常保护和范围过滤

ros_robot_controller_sdk.py:
  bus_servo_read_and_unpack 增加 1.0s timeout
  读命令前清理 stale queue
  queue.Empty / struct.error 返回 None
```

修复后最小控制栈可以稳定通过 preflight：

```text
/ros_robot_controller: online
/controller_manager: online
/servo_manager: online
/arm_controller: online
/gripper_controller: online
/ros_robot_controller/bus_servo/set_position: Subscription count = 1
/servo_controller: Subscription count = 1
/ros_robot_controller/init_finish: success=True
/controller_manager/init_finish: success=True
```

但是 Direct Board SDK 只读诊断暴露出更底层的阻断项：

```text
ARM_POWER_UNDERVOLTAGE
  ID 1-5 vin ~= 6.1-6.6V
  ID 10 vin ~= 4.258V
  低于教程中 HX 总线舵机 DC 9-12.6V 工作范围

ARM_TORQUE_DISABLED_OR_UNVERIFIED
  ID 1/2/3/4/5/10 torque_state 均为 [0]
  torque_state 的具体语义需要结合厂家工具和小动作读回确认

ARM_SERVO_ID3_POSITION_INVALID
  ID 3 present_id=[3]
  position=[-92]
  超出 0-1000 有效脉宽/位置范围

ARM_POSITION_READBACK_PARTIAL
  ID 1/2/4/5/10 position-only 读回稳定
  ID 3 在线但 position 无效
```

因此当前不要继续重复“发动作组 -> 看控制台动作完成”。下一轮主线应改为：

```text
供电恢复到 9-12.6V
-> 确认 torque_state 语义和扭矩状态
-> 修复/校准 ID 3 position 异常
-> 最小栈 preflight
-> 单 ID / 全 ID 读回
-> 小幅夹爪动作
-> camera_up / horizontal / 多角度动作组
-> PNG 差异和人工目检
-> AgenticOS bridge allowlist
```

在 `ARM_POWER_UNDERVOLTAGE`、`ARM_SERVO_ID3_POSITION_INVALID` 没有解除前，不能把任何动作写成真实运动成功。

## 2. 教程里的关键依据

从 `/home/ubuntu/8.机械臂运动控制.pdf` 中可提取出几个关键点：

1. 机械臂使用总线舵机，UART 串口通信，波特率 `115200`。
2. 舵机控制范围为 `0-1000`，对应约 `0-240` 度。
3. 舵机 ID：

   ```text
   1 号：云台 / 底座水平旋转
   2、3、4 号：机械臂关节
   5 号：腕部
   10 号：夹爪
   ```

4. 动作组路径：

   ```text
   /home/ubuntu/software/arm_pc/ActionGroups
   ```

5. 教程多次要求在使用上位机或单独调试舵机前先关闭 APP 自启服务：

   ```bash
   sudo systemctl stop start_app_node.service
   ```

6. 教程明确说明：如果已经开启舵机相关节点，不能再打开上位机或舵机工具，因为串口会被占用。
7. 夹爪 `10` 号舵机建议范围：

   ```text
   200-700
   ```

这些点和当前现象吻合：如果 `start_app_node.service`、手动 launch、上位机、AgenticOS bridge 同时竞争总线串口，会出现 ROS 状态看起来正常，但真实机械臂不动或后端节点崩溃。

## 3. 当前发现的具体代码/驱动状态

本地 driver 源码已经修复上一轮发现的直接软件崩溃点。

文件：

```text
/home/ubuntu/ros2_ws/src/driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_node.py
/home/ubuntu/ros2_ws/src/driver/ros_robot_controller/ros_robot_controller/ros_robot_controller_sdk.py
```

已修复内容：

```text
bus_servo_read_voltage -> bus_servo_read_vin
bus_servo_read_torque  -> bus_servo_read_torque_state
bus_servo_read_and_unpack(timeout=1.0)
无效 uint16 / int16 / position / torque_state 读回过滤
单个 ID 异常不再导致 ros_robot_controller 进程退出
```

当前软件层状态：

```text
position-only 单 ID 读回不再杀死后端
ID 1/2/4/5/10 position 可稳定读回
ID 3 在线但 position 原始值为 -92，已被 ROS 层过滤为空
voltage / torque_state 只读查询已经可以用于诊断，但必须保持只读
```

当前硬件/总线阻断：

```text
vin 不满足 9-12.6V 工作范围
torque_state 均为 [0]，需要确认语义和真实扭矩状态
ID 3 position 异常
```

所以下一轮调通的重点不是继续改 Agent App，也不是扩大动作组，而是先建立“硬件健康门”：

```text
供电健康
扭矩状态可解释
ID 3 position 恢复到 0-1000
最小栈读回稳定
小动作真实变化
```

只有这些条件满足后，才允许进入 `camera_up`、`horizontal`、`detect_left/right`、`left_up/down`、`right_up/down` 等动作组验证。

## 4. 手动 ROS 调试的正确模式

手动摸索机械臂时，先进入“单一串口拥有者”模式。

### 4.1 停掉自启服务

```bash
sudo systemctl stop start_app_node.service
```

确认服务已停：

```bash
systemctl status start_app_node.service
```

如果还有残留 ROS 节点，可使用教程建议的停止脚本：

```bash
~/.stop_ros.sh
```

然后确认没有旧的控制节点：

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash

ros2 node list | grep -E 'ros_robot_controller|controller_manager|servo_manager|init_pose'
```

### 4.2 启动最小机械臂控制栈

终端 A：

```bash
export need_compile=False
export MACHINE_TYPE=ROSOrin_Mecanum_Pro
export DEPTH_CAMERA_TYPE=aurora

source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash

ros2 launch ros_robot_controller ros_robot_controller.launch.py
```

终端 B：

```bash
export need_compile=False
export MACHINE_TYPE=ROSOrin_Mecanum_Pro
export DEPTH_CAMERA_TYPE=aurora

source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash

ros2 launch servo_controller servo_controller.launch.py base_frame:=base_footprint
```

不要一开始启动完整 `bringup` 或 OpenClaw 全套玩法。先把最小硬件控制链路跑通。

### 4.3 验证硬件后端在线

必须看到 `/ros_robot_controller` 在线：

```bash
ros2 node list | grep ros_robot_controller
```

必须看到底层 bus topic 有订阅者：

```bash
ros2 topic info /ros_robot_controller/bus_servo/set_position
```

期望：

```text
Subscription count: 1
```

验证两个 init service：

```bash
ros2 service call /ros_robot_controller/init_finish std_srvs/srv/Trigger "{}"
ros2 service call /controller_manager/init_finish std_srvs/srv/Trigger "{}"
```

### 4.4 只读读取舵机位置

只读 position，不要读 voltage/torque：

```bash
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [
    {id: 1, get_position: 1},
    {id: 2, get_position: 1},
    {id: 3, get_position: 1},
    {id: 4, get_position: 1},
    {id: 5, get_position: 1},
    {id: 10, get_position: 1}
  ]}"
```

如果某个 ID 返回空，例如 `3` 号为空，优先排查：

1. 该舵机 ID 是否正确。
2. 总线连接是否松动。
3. 舵机供电是否正常。
4. 舵机是否进入保护状态。
5. 上位机是否能读到该 ID。

如果 position-only 读回导致节点退出，不允许继续发运动命令。进入下面的“读回稳定性修复循环”。

### 4.4.1 读回稳定性回归检查

最新报告显示：本地 driver 修复后，position-only 读回不再导致 `ros_robot_controller` 崩溃。下一轮仍要保留回归检查，防止旧环境、未 source 新 install、或自启服务覆盖导致问题复现。

必须保存 `ros_robot_controller` 和 `servo_controller` 的完整 stdout/stderr 日志，然后按单 ID 到全 ID 的顺序读取：

```text
只读 ID 1
只读 ID 2
只读 ID 3
只读 ID 4
只读 ID 5
只读 ID 10
全量读取 ID 1/2/3/4/5/10
```

如果任一读回导致后端死亡：

```text
ARM_BACKEND_DIED
ARM_SERVO_POSITION_READBACK_FAILED
servo_id: <id or all>
```

然后回到 driver 日志和 build/source 检查，不能继续发运动命令。

当前已知读回结果应被解释为：

```text
ID 1: position 可读
ID 2: position 可读
ID 3: present_id 可读，但 position 无效
ID 4: position 可读
ID 5: position 可读
ID 10: position 可读
```

这不是可运动状态，只能说明 driver 不再崩溃。

### 4.4.2 硬件健康门

position-only 读回稳定后，先做只读硬件健康检查，不发运动。

读取 position / vin / torque_state / temperature：

```bash
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [
    {id: 1, get_position: 1, get_voltage: 1, get_torque_state: 1, get_temperature: 1},
    {id: 2, get_position: 1, get_voltage: 1, get_torque_state: 1, get_temperature: 1},
    {id: 3, get_position: 1, get_voltage: 1, get_torque_state: 1, get_temperature: 1},
    {id: 4, get_position: 1, get_voltage: 1, get_torque_state: 1, get_temperature: 1},
    {id: 5, get_position: 1, get_voltage: 1, get_torque_state: 1, get_temperature: 1},
    {id: 10, get_position: 1, get_voltage: 1, get_torque_state: 1, get_temperature: 1}
  ]}"
```

健康门通过条件：

```text
每个在线舵机 present_id 正确
ID 1/2/3/4/5/10 position 均在 0-1000
vin 在 9000-12600mV，至少不能低于教程工作电压下限
temperature 低于舵机温度限制
torque_state 语义已确认，且真实小动作前处于可执行状态
```

当前最新报告未通过：

```text
vin: 4.258-6.6V -> ARM_POWER_UNDERVOLTAGE
ID 3 position: -92 -> ARM_SERVO_ID3_POSITION_INVALID
torque_state: [0] -> ARM_TORQUE_DISABLED_OR_UNVERIFIED
```

处理顺序：

1. 检查机械臂舵机电源 rail、电池、DC-DC、保险丝、急停/保护开关，让 bus servo vin 回到 9-12.6V。
2. 重新插拔并检查 ID 3 相关总线线缆、接口和舵机本体。
3. 停止 `start_app_node.service` 后，用厂家 Arm 上位机读取 ID 3 position；如果厂家工具也读到负数/异常，优先校准或更换 ID 3 舵机。
4. 在电压健康前，不启用扭矩，不发送动作组，不发送夹爪动作。
5. 电压健康后，再最小幅度验证 torque_state 语义：只做可回退、小范围、单舵机或夹爪动作，并立即读回 position。

如果健康门不通过，Robot Photographer / AgenticOS bridge 必须返回结构化错误：

```text
ARM_POWER_UNDERVOLTAGE
ARM_TORQUE_DISABLED_OR_UNVERIFIED
ARM_SERVO_ID3_POSITION_INVALID
ARM_HEALTH_GATE_FAILED
```

### 4.5 小幅真实运动测试

只有 `4.4.2` 硬件健康门通过后，才能进入本节。

先只测试夹爪 `10` 号，范围控制在教程建议的 `200-700` 内。

打开一点：

```bash
ros2 topic pub --once /servo_controller \
  servo_controller_msgs/msg/ServosPosition \
  "{duration: 1.0, position_unit: 'pulse', position: [{id: 10, position: 540.0}]}"
```

回到中间：

```bash
ros2 topic pub --once /servo_controller \
  servo_controller_msgs/msg/ServosPosition \
  "{duration: 1.0, position_unit: 'pulse', position: [{id: 10, position: 500.0}]}"
```

然后再次 position-only 读回：

```bash
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 10, get_position: 1}]}"
```

如果夹爪也不动，先不要继续测试大关节，直接回到硬件/串口排查。

判定规则：

```text
命令发布成功但 position 不变 -> ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED
position 变化但后端随后死亡 -> ARM_BACKEND_DIED_AFTER_MOTION
position 变化且可回到初始附近 -> 可进入动作组测试
```

### 4.6 动作组测试

动作组文件位于：

```bash
ls /home/ubuntu/software/arm_pc/ActionGroups
```

推荐先测：

```text
init
camera_up
horizontal
```

当前已经存在的多角度候选动作组：

```text
detect_left.d6a
detect_right.d6a
left_up.d6a
left_down.d6a
right_up.d6a
right_down.d6a
horizontal.d6a
camera_up.d6a
init.d6a
```

这些名字只能作为后端候选，不直接暴露给 Agent App。验证通过后，再由 AgenticOS robot profile 映射成业务 named pose：

```text
init / horizontal        -> camera_center 或 arm_home，需实测决定
detect_left             -> camera_yaw_left_15，需实测决定
detect_right            -> camera_yaw_right_15，需实测决定
left_up / right_up      -> camera_pitch_up_15 或组合姿态，需实测决定
left_down / right_down  -> 不得直接映射为 camera_pitch_down_15；需创建并验证独立安全 camera_down 动作后再开放
camera_up               -> camera_up，已存在候选但仍需真实运动验证
```

如果动作组文件存在但真实运动未被 position 或图像证据确认，bridge 必须返回：

```text
ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED
```

如果动作组文件缺失，返回：

```text
ARM_ACTION_BACKEND_MISSING
CAMERA_POSE_BACKEND_MISSING
```

用 `init_pose.launch.py` 发动作组：

```bash
ros2 launch controller init_pose.launch.py action_name:=camera_up
```

动作完成后可 `Ctrl+C` 退出该 launch。再测：

```bash
ros2 launch controller init_pose.launch.py action_name:=init
```

如果要用 OpenClaw 的命名动作节点：

终端 C：

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash

ros2 run openclaw_controller claw_arm_group_control
```

另一个终端：

```bash
ros2 service call /claw_arm_group_control/arm_group_status std_srvs/srv/Trigger "{}"

ros2 topic pub --once /claw_arm_group_control/arm_group_control \
  std_msgs/msg/String \
  "{data: 'camera_up'}"
```

`claw_arm_group_control` 当前源码只允许：

```text
init
camera_up
voice_pick
voice_give
```

## 5. 相机图像验证

如果相机确实安装在机械臂/云台上，那么大幅动作后图像应明显变化。  
如果相机固定在车体上，则图像变化不能作为机械臂运动证据，需要依赖舵机位置回读或外部观察。

### 5.1 单独启动相机

如果已停掉 `start_app_node.service`，可单独启动相机：

```bash
export need_compile=False
export DEPTH_CAMERA_TYPE=aurora

source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash

ros2 launch peripherals depth_camera.launch.py
```

检查相机：

```bash
ros2 topic info /depth_cam/rgb0/image_raw
ros2 topic hz /depth_cam/rgb0/image_raw
```

### 5.2 图像变化阈值

对于大幅运动，建议使用下面两个指标判断：

```text
mean_abs_diff > 10
changed_pixels_gt25_pct > 5%
```

如果低于这个水平，不能说“相机视角已明显改变”。

当前测试中，恢复后动作的结果是：

```text
mean_abs_diff ~= 1.3
changed_pixels_gt25_pct = 0%
```

这属于未确认运动。

## 6. 不推荐的操作

在 vendor driver 未修复前，不推荐执行：

```bash
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 1, get_voltage: 1}]}"
```

也不推荐：

```bash
ros2 service call /ros_robot_controller/bus_servo/get_state \
  ros_robot_controller_msgs/srv/GetBusServoState \
  "{cmd: [{id: 1, get_torque_state: 1}]}"
```

原因：

```text
ros_robot_controller_node.py 调用了 SDK 中不存在的方法，可能导致节点退出。
```

最新本地修复 build/source 生效后，`get_voltage` 和 `get_torque_state` 可以作为只读健康门诊断使用。这里保留“未修复前不推荐”的原因，是为了防止切回旧 install、旧服务或未 source 新工作区时再次触发后端崩溃。

也不建议在 `start_app_node.service` 运行时再打开上位机、舵机工具或手动 launch 另一套控制节点。教程已经说明这会阻塞串口通信。

## 7. 对 AgenticOS / Robot Photographer 的改造要求

Robot Photographer 不应该把“动作组发出”当作成功。bridge/HAL 必须增加真实后端检查。

### 7.1 preflight

每次机械臂动作前检查：

```text
/ros_robot_controller node 存在
/controller_manager node 存在
/ros_robot_controller/bus_servo/set_position Subscription count == 1
/servo_controller Subscription count == 1
```

如果失败，返回：

```text
ARM_BACKEND_UNAVAILABLE
```

preflight 通过后还必须执行硬件健康门：

```text
position readback for ID 1/2/3/4/5/10
vin readback for ID 1/2/3/4/5/10
torque_state readback for ID 1/2/3/4/5/10
temperature readback for ID 1/2/3/4/5/10
```

如果电压不足、ID3 position 异常、torque_state 未确认或不可执行，返回：

```text
ARM_HEALTH_GATE_FAILED
ARM_POWER_UNDERVOLTAGE
ARM_SERVO_ID3_POSITION_INVALID
ARM_TORQUE_DISABLED_OR_UNVERIFIED
```

### 7.2 状态查询边界

在确认本地 driver 修复已经 build/source 前，bridge 不得请求：

```text
get_voltage
get_torque_state
```

只能使用：

```text
get_position
```

否则返回：

```text
ARM_STATUS_QUERY_UNSAFE
```

在本地 driver 修复已生效后，`get_voltage` 和 `get_torque_state` 可作为只读健康门诊断使用，但仍然禁止把状态查询当作动作成功证据。动作成功必须依赖 position 变化、图像变化或硬件后端真实完成状态。

### 7.3 动作成功判定

动作执行后，必须满足至少一个真实证据：

1. position-only bus 读回变化达到预期。
2. 相机图像变化达到阈值。
3. 外部硬件 backend 明确返回真实完成状态。

如果只有 `/controller_manager/servo_states` 变化，不能判定成功。应返回：

```text
ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED
```

### 7.4 多角度拍摄 allowlist

在当前问题解决前，不应把这些动作加入 Robot Photographer 的“已验证多角度姿态”：

```text
detect_left
detect_right
horizontal
left_up
left_down
right_up
right_down
```

它们只能作为 backend candidate。必须先通过：

```text
真实动作 -> PNG 证据 -> 差异阈值 -> 人工目检
```

然后才能进入 allowlist。

### 7.5 推荐新增错误码

```text
ARM_BACKEND_UNAVAILABLE
ARM_BACKEND_DIED
ARM_BACKEND_DIED_AFTER_MOTION
ARM_HEALTH_GATE_FAILED
ARM_POWER_UNDERVOLTAGE
ARM_TORQUE_DISABLED_OR_UNVERIFIED
ARM_STATUS_QUERY_UNSAFE
ARM_SERVO_POSITION_READBACK_FAILED
ARM_SERVO_ID3_POSITION_INVALID
ARM_ACTION_NO_PHYSICAL_MOTION_CONFIRMED
CAMERA_ANGLE_DIFFERENCE_TOO_SMALL
CAMERA_NOT_ATTACHED_TO_ARM_POSE
```

## 8. driver 修复状态与后续边界

这部分属于机器人 ROS2 driver，本地源码已经做过一次有限修复。后续仍要遵守边界：Agent App、AgenticOS Runtime、SDK 不得私自绕过 bridge 控制硬件；如需继续改 driver，范围只能限定在本地 ROS2 工作区：

```text
/home/ubuntu/ros2_ws/src/driver/ros_robot_controller
```

仍然不能修改：

```text
/opt/ros
MoveIt
Nav2
机器人上游 vendor 驱动仓库
AgenticOS Runtime / SDK / Agent Apps 的 ROS 边界
```

已完成的 driver 修复：

```text
bus_servo_read_voltage -> bus_servo_read_vin
bus_servo_read_torque  -> bus_servo_read_torque_state
bus_servo_read_and_unpack(timeout=1.0)
stale queue 清理
queue.Empty / struct.error 返回 None
position 只接受 0-1000
torque_state 只接受 0-1
无效读回不再导致 ROS message assignment 崩溃
```

每次硬件修复或重启后仍建议重新 build/source 并跑回归：

```bash
cd /home/ubuntu/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select ros_robot_controller servo_controller
source /home/ubuntu/ros2_ws/install/setup.bash
```

下一步不要优先继续改 driver，除非出现新的 traceback 或读回再次导致后端死亡。当前优先级：

```text
1. 恢复舵机供电到 9-12.6V。
2. 校准/修复 ID 3 position 异常。
3. 确认 torque_state 语义和真实扭矩状态。
4. 健康门通过后才发最小运动命令。
```

## 9. 推荐执行顺序

### 9.1 硬件恢复阶段

1. 停掉 `start_app_node.service`，进入单一串口拥有者模式。
2. 确认没有旧的 `ros_robot_controller` / `controller_manager` / `servo_controller` 残留。
3. 检查机械臂舵机电源 rail、电池、DC-DC、保险丝、急停/保护开关。
4. 让 ID 1/2/3/4/5/10 的 bus servo vin 恢复到教程工作范围 `9-12.6V`。
5. 重点检查 ID 3 线缆、接口、舵机本体和 ID 映射。
6. 用厂家 Arm 上位机或 Direct Board SDK 只读确认 ID 3 position 回到 `0-1000`。
7. 确认 torque_state 语义：不要只看字段名，要用厂家工具或最小幅度动作验证它和真实扭矩的关系。

### 9.2 ROS 最小栈阶段

1. build/source 本地 driver：

   ```bash
   cd /home/ubuntu/ros2_ws
   source /opt/ros/humble/setup.bash
   colcon build --symlink-install --packages-select ros_robot_controller servo_controller
   source /home/ubuntu/ros2_ws/install/setup.bash
   ```

2. 单独启动 `ros_robot_controller`。
3. 单独启动 `servo_controller`。
4. 执行 backend preflight。
5. 单 ID position-only 读回 1/2/3/4/5/10。
6. 全量 position-only 读回 1/2/3/4/5/10。
7. 只读硬件健康门：position / vin / torque_state / temperature。
8. 健康门未通过就停止，不发送运动。

### 9.3 小动作阶段

1. 健康门通过后，先测试 10 号夹爪 `500 -> 540 -> 500`。
2. 每一步后读回 ID 10 position。
3. 确认 position 变化且能回到初始附近。
4. 后端不得崩溃，`/ros_robot_controller/bus_servo/set_position` 和 `/servo_controller` 必须仍在线。

### 9.4 动作组阶段

1. 测 `camera_up -> init`。
2. 测 `horizontal -> init`。
3. 依次测候选多角度动作：

   ```text
   detect_left -> horizontal/init
   detect_right -> horizontal/init
   left_up -> horizontal/init
   left_down -> horizontal/init
   right_up -> horizontal/init
   right_down -> horizontal/init
   ```

4. 每个动作都记录：

   ```text
   command
   start positions
   end positions
   vin before/after
   torque_state before/after
   backend alive after action
   recovery action result
   ```

5. 任何动作不能回到安全姿态，就停止后续动作并返回明确错误。

### 9.5 相机与多角度拍摄阶段

1. 单独启动相机，保存动作前 PNG。
2. 每个动作组后保存 PNG + metadata。
3. 计算图像差异：

   ```text
   mean_abs_diff
   changed_pixels_gt25_pct
   hist_distance
   phash_distance
   ```

4. 对中心、左、右、上、下照片做人工目检。
5. 如果数值差异过小或视觉上不明显，返回：

   ```text
   CAMERA_ANGLE_DIFFERENCE_TOO_SMALL
   ANGLE_DIFFERENCE_NOT_VISUALLY_CONFIRMED
   ```

### 9.6 AgenticOS 回接阶段

1. 只有通过真实运动和图像验证的动作组，才能加入 robot profile。
2. robot profile 用业务 named pose 暴露，不暴露原始动作组名。
3. 更新 Robot Photographer policy/schema allowlist。
4. 运行 `real_robot_multi_angle_photo_acceptance.sh`。
5. 用 `AGENTIC_REAL_ROBOT_ALLOW_ARM_MOTION=1 agentic photo --real --allow-arm-motion --yes "拍一组多角度照片并验证差异"` 做最终验收。

## 10. 成功标准

一次成功的机械臂动作测试必须同时具备：

```text
ros_robot_controller 在线
bus_servo/set_position 有订阅者
动作命令发布成功
真实舵机 position-only 读回合理变化，或相机图像明显变化
ros_robot_controller 未崩溃
动作后能回 init
```

如果缺少任何一项，都不能写成“机械臂运动成功”。
