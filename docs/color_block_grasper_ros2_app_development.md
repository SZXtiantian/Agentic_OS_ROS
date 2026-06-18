# 传统 ROS2 彩色方块夹取应用开发文档

最后更新：2026-06-18

本文用于指导后续 Codex `goal` 实现一个传统 ROS2 应用：用户通过命令行指定颜色，机器人使用 RGB-D 相机识别对应颜色方块，并通过机械臂和爪子完成夹取。

重要约束：

- 这是 `/home/ubuntu/ros2_ws/src` 下的普通 ROS2 应用，不是 Agentic App。
- 新应用可以 import `rclpy`，因为它属于机器人 ROS2 应用层。
- 新应用不能放进 `Agentic_OS_ROS_publish/agentic_apps`。
- 新应用不能依赖 `/claw_track_and_grab/*` 服务作为运行时后端。
- `/claw_track_and_grab` 只能作为参考代码：参考其颜色分割、深度取点、手眼变换、稳定判断、IK 调用和舵机动作思路。
- 新应用应该自己订阅 RGB-D 话题、自己完成目标检测和抓取状态机，只依赖底层相机、kinematics 和 servo controller。

---

## 1. 目标

新增 ROS2 包：

```text
/home/ubuntu/ros2_ws/src/color_block_grasper
```

实现传统命令行体验：

```bash
ros2 run color_block_grasper color_block_grasp_cli --color red --timeout 45
```

可选抓取后放置：

```bash
ros2 run color_block_grasper color_block_grasp_cli --color red --timeout 45 --place
```

也提供 launch 入口：

```bash
ros2 launch color_block_grasper color_block_grasper.launch.py target_color:=red auto_start:=true
```

MVP 目标：

1. 命令行指定目标颜色。
2. 从 RGB-D 相机获取彩色图、深度图、相机内参。
3. 基于 LAB 阈值检测目标颜色方块。
4. 从深度图估算目标距离。
5. 将目标像素点转换为相机 3D 坐标。
6. 将相机坐标转换为机械臂坐标。
7. 调用 `/kinematics/set_pose_target` 求解机械臂舵机脉宽。
8. 通过 `/servo_controller` 控制机械臂和爪子完成夹取。
9. 输出结构化状态和错误码。
10. 必须在真实硬件上调到能够夹起指定颜色方块为止；如果第一次不能夹起，需要继续调整视觉阈值、深度补偿、手眼偏移、夹取高度、爪子开合值和动作时序，直到实物抓取成功。

本项目的最终目标不是“代码写完”或“节点能启动”，而是：

```text
用户执行一条命令 -> 机器人识别指定颜色方块 -> 机械臂靠近 -> 爪子夹住 -> 方块被实际提离桌面
```

如果真实测试失败，不能把任务标记为完成。必须记录失败原因，继续调参或修正实现，直到至少完成一次真实成功夹取。

## 当前实现快照

截至 2026-06-18，`/home/ubuntu/ros2_ws/src/color_block_grasper` 已经落地为独立 ROS2 package：

- `color_block_grasp_cli`：抓取 CLI，支持 dry-run、调试图、目标选择、LAB 配置、深度补偿、手眼偏移、抓取验证和可选 `--place`。
- `color_block_place_cli`：放置 CLI，使用已成功抓取轨迹的反向/释放动作，支持自定义 lift/pick/pregrasp pulses。
- `color_block_grasper_node.py`：ROS2 节点和抓取状态机。
- `color_config.py`、`vision.py`、`depth_geometry.py`、`motion.py`、`verification.py`、`options.py`、`status.py`：颜色、视觉、深度几何、运动、抓取验证、参数和结构化结果模块。
- `config/lab_tuned.yaml`：现场调参后的 red / blue / green LAB 配置。
- `docs/hardware_debug_log.md`：硬件调试记录。
- `test/`：CLI、颜色配置、深度几何、运动、放置和验证单元测试。

当前 field-tuned 命令以 ROS2 package README 为准：

```bash
ros2 run color_block_grasper color_block_grasp_cli \
  --color blue \
  --lab-config /home/ubuntu/ros2_ws/src/color_block_grasper/config/lab_tuned.yaml \
  --timeout 90 \
  --target-selection bottommost \
  --allow-unsafe-gripper \
  --gripper-open 150 \
  --gripper-close 700 \
  --verify-pick
```

放置当前已夹持方块：

```bash
ros2 run color_block_grasper color_block_place_cli \
  --allow-unsafe-gripper \
  --gripper-open 150 \
  --gripper-close 700
```

---

## 2. 现有资料只作参考

### 2.1 机械臂控制指南

参考文档：

```text
/home/ubuntu/8.机械臂运动控制.pdf
```

已确认的关键信息：

- 机械臂由总线舵机控制。
- 舵机控制范围是 `0-1000`，对应 `0-240°`。
- 舵机 ID：
  - `1`：云台 / 底座旋转
  - `2`、`3`、`4`：机械臂主要关节
  - `5`：腕部
  - `10`：爪子
- 爪子 ID `10` 有机械限位，指南建议安全范围为 `[200, 700]`。
- 有效夹取半径建议不超过约 `30cm`。
- 自动程序运行时不要同时使用占用舵机通信的上位机调试工具。

### 2.2 抓取参考代码

参考文件：

```text
/home/ubuntu/ros2_ws/src/openclaw_controller/openclaw_controller/claw_track_and_grab/claw_track_and_grab.py
```

该文件只能参考，不能作为新 app 的服务后端。

可以参考的内容：

- `ColorTracker` 的 LAB 颜色分割方法。
- `depth_pixel_to_camera()` 的像素 + 深度转相机坐标公式。
- `hand2cam_tf_matrix` 的相机到末端坐标变换矩阵。
- 目标中心附近 ROI 深度取均值的方法。
- 目标稳定后再夹取的逻辑。
- 调用 `/kinematics/get_current_pose` 和 `/kinematics/set_pose_target` 的方式。
- 使用 `servo_controller.bus_servo_control.set_servo_position()` 发布舵机动作的方式。

不能直接依赖的内容：

- 不能调用 `/claw_track_and_grab/init_pose`。
- 不能调用 `/claw_track_and_grab/set_color`。
- 不能调用 `/claw_track_and_grab/start`。
- 不能调用 `/claw_track_and_grab/start_pick`。
- 不能调用 `/claw_track_and_grab/pick_status`。
- 不能调用 `/claw_track_and_grab/place`。
- 不能调用 `/claw_track_and_grab/stop`。
- 不能要求 `/claw_track_and_grab` 节点运行。

这些服务名字最多用于理解“一个抓取应用大概需要哪些生命周期阶段”，不能成为新应用 API。

### 2.3 可直接使用的底层接口

新应用应该直接使用这些底层 ROS2 接口：

相机话题：

```text
/depth_cam/rgb0/image_raw
/depth_cam/depth0/image_raw
/depth_cam/depth0/camera_info
```

机械臂逆解服务：

```text
/kinematics/get_current_pose
/kinematics/set_pose_target
```

舵机控制话题：

```text
/servo_controller
```

可参考的底层 Python helper：

```text
kinematics.kinematics_control.set_pose_target
servo_controller.bus_servo_control.set_servo_position
```

这些 helper 属于现有机器人 ROS2 应用栈的底层能力，和 `/claw_track_and_grab` 这种具体业务节点不同。

---

## 3. 推荐架构

新应用采用独立 ROS2 节点实现：

```text
User CLI
  -> color_block_grasp_cli
  -> color_block_grasper_node
  -> RGB-D subscriptions
  -> color segmentation
  -> depth estimation
  -> camera-to-arm transform
  -> /kinematics/set_pose_target
  -> /servo_controller
  -> arm + gripper
```

不要这样做：

```text
User CLI
  -> color_block_grasp_cli
  -> /claw_track_and_grab/* services
  -> existing grasp backend
```

这个禁止路径虽然实现快，但会把新应用绑死在一个“写得未必好的旧 app”上，不适合作为后续可维护的传统 ROS2 app。

---

## 4. ROS2 包结构

建议目录：

```text
/home/ubuntu/ros2_ws/src/color_block_grasper
  package.xml
  setup.py
  resource/color_block_grasper
  color_block_grasper/__init__.py
  color_block_grasper/color_block_grasp_cli.py
  color_block_grasper/color_block_grasper_node.py
  color_block_grasper/color_config.py
  color_block_grasper/vision.py
  color_block_grasper/depth_geometry.py
  color_block_grasper/motion.py
  color_block_grasper/options.py
  color_block_grasper/status.py
  color_block_grasper/verification.py
  launch/color_block_grasper.launch.py
  config/lab_tuned.yaml
  docs/hardware_debug_log.md
  test/test_import.py
  test/test_color_config.py
  test/test_depth_geometry.py
  test/test_motion.py
  test/test_cli.py
  test/test_place_cli.py
  test/test_verification.py
```

职责划分：

| 文件 | 职责 |
| --- | --- |
| `color_block_grasp_cli.py` | 命令行参数解析，启动节点，等待结果，打印 JSON |
| `color_block_grasper_node.py` | ROS2 节点、订阅、状态机、服务/动作协调 |
| `color_config.py` | 读取 LAB 颜色阈值配置 |
| `vision.py` | 颜色分割、轮廓选择、目标中心计算 |
| `depth_geometry.py` | 深度 ROI、像素到相机坐标、坐标变换 |
| `motion.py` | 初始姿态、IK 请求、夹取、抬起、放置、复位 |
| `options.py` | CLI 和 launch 参数的结构化配置 |
| `verification.py` | 抓取后视觉验证 |
| `status.py` | 状态枚举、错误码、JSON 输出结构 |

---

## 5. package.xml 依赖

建议依赖：

```xml
<depend>rclpy</depend>
<depend>sensor_msgs</depend>
<depend>std_msgs</depend>
<depend>std_srvs</depend>
<depend>geometry_msgs</depend>
<depend>cv_bridge</depend>
<depend>message_filters</depend>
<depend>servo_controller_msgs</depend>
<depend>kinematics_msgs</depend>
<depend>servo_controller</depend>
<depend>kinematics</depend>
```

Python 侧需要：

```text
opencv-python / cv2
numpy
PyYAML
```

如果系统已通过 ROS apt 包提供 `cv2`、`numpy`、`yaml`，不需要在 `setup.py` 里额外 pip 安装。

---

## 6. 命令行接口

### 6.1 单次抓取

```bash
ros2 run color_block_grasper color_block_grasp_cli --color red
```

参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--color` | 必填 | 目标颜色 |
| `--timeout` | `45` | 抓取总超时时间 |
| `--place` | `false` | 抓取后是否放置 |
| `--dry-run` | `false` | 只检查配置和底层服务，不运动 |
| `--show-image` | `false` | 是否打开 OpenCV 显示窗口 |
| `--debug-image-topic` | `true` | 是否发布检测结果图 |
| `--min-area` | `50` | 最小目标轮廓面积 |
| `--stable-seconds` | `2.0` | 目标稳定多久后开始夹取 |
| `--max-distance-m` | `0.35` | 最大允许夹取距离 |
| `--place-x` | 可选 | 自定义放置点 X |
| `--place-y` | 可选 | 自定义放置点 Y |
| `--place-z` | 可选 | 自定义放置点 Z |

### 6.2 launch 入口

```bash
ros2 launch color_block_grasper color_block_grasper.launch.py target_color:=red auto_start:=true
```

launch 参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `target_color` | `red` | 目标颜色 |
| `auto_start` | `true` | 启动后是否自动抓取一次 |
| `place_after_pick` | `false` | 是否抓取后放置 |
| `pick_timeout_s` | `45` | 总超时 |
| `show_image` | `false` | 是否显示检测窗口 |
| `debug_image_topic` | `true` | 是否发布检测结果图 |

---

## 7. 颜色配置

优先读取：

```text
/home/ubuntu/software/lab_tool/lab_config.yaml
```

读取路径：

```text
lab -> Stereo -> <target_color>
```

示例逻辑：

```python
color = config["lab"]["Stereo"][target_color]
lower = tuple(color["min"])
upper = tuple(color["max"])
```

如果颜色不存在，必须在运动前失败：

```text
INVALID_COLOR
```

不要为了“试一下”在颜色缺失时继续运行。颜色阈值不可靠时，机器人会追错物体。

---

## 8. 视觉算法

`vision.py` 建议实现：

```text
ColorSegmenter
TargetObservation
detect_largest_target(image_bgr, color_range, min_area)
```

处理流程：

1. 将 RGB 图转 BGR 或确认输入编码。
2. 缩放到一半尺寸做检测，减少噪声和计算量。
3. 高斯模糊。
4. 转 LAB。
5. `cv2.inRange()` 得到 mask。
6. 腐蚀 + 膨胀。
7. 查找外轮廓。
8. 过滤小面积轮廓。
9. 选择目标轮廓。
10. 输出中心点、半径、面积、mask/debug image。

目标选择策略：

- MVP 可以选择面积最大的目标。
- 如果相机斜向下且同色多目标，参考旧代码可选择画面更下方的目标。
- 选择策略需要写成参数：

```text
target_selection:=largest
target_selection:=bottommost
```

---

## 9. 深度与坐标变换

`depth_geometry.py` 建议实现：

```text
estimate_depth_from_roi(depth_image, center_x, center_y, roi_radius_px)
depth_pixel_to_camera(pixel_coords, depth_m, intrinsics)
camera_to_arm_position(camera_position, endpoint_pose, hand2cam_tf_matrix)
```

### 9.1 深度 ROI

在目标中心附近取 ROI：

```text
center_y - 5 : center_y + 5
center_x - 5 : center_x + 5
```

过滤无效深度：

```text
depth > 0
depth < 10000mm
```

取均值并转换为米：

```text
depth_m = mean(valid_depth_mm) / 1000.0
```

可以保留补偿参数，但必须参数化：

```text
object_radius_compensation_m := 0.02
depth_error_compensation_m := 0.025
```

### 9.2 像素到相机坐标

公式：

```python
x = (px - cx) * depth / fx
y = (py - cy) * depth / fy
z = depth
```

内参来自：

```text
sensor_msgs/msg/CameraInfo.k
```

即：

```python
fx = K[0]
fy = K[4]
cx = K[2]
cy = K[5]
```

### 9.3 相机到机械臂坐标

可参考旧代码中的矩阵：

```python
hand2cam_tf_matrix = [
    [0.0, 0.0, 1.0, -0.101],
    [-1.0, 0.0, 0.0, 0.0],
    [0.0, -1.0, 0.0, 0.037],
    [0.0, 0.0, 0.0, 1.0],
]
```

但不要硬编码死在算法里。建议作为 ROS 参数：

```text
hand2cam.tx := -0.101
hand2cam.ty := 0.0
hand2cam.tz := 0.037
```

MVP 可以先使用与旧代码相同的默认矩阵，后续再根据实测标定修正。

---

## 10. 运动控制

`motion.py` 建议实现：

```text
ArmMotionController
  wait_ready()
  go_init_pose()
  track_target(center)
  pick_at(position)
  lift()
  place()
  go_home()
  stop()
```

底层接口：

```python
from servo_controller_msgs.msg import ServosPosition
from servo_controller.bus_servo_control import set_servo_position
from kinematics_msgs.srv import GetRobotPose, SetRobotPose
from kinematics.kinematics_control import set_pose_target
```

发布器：

```python
self.joints_pub = self.create_publisher(ServosPosition, "/servo_controller", 1)
```

服务客户端：

```python
self.get_current_pose_client = self.create_client(GetRobotPose, "/kinematics/get_current_pose")
self.set_pose_target_client = self.create_client(SetRobotPose, "/kinematics/set_pose_target")
```

### 10.1 初始姿态

旧代码中的姿态可作为参考：

```text
(1, 500), (2, 630), (3, 151), (4, 140), (5, 500), (10, 150)
```

但注意 PDF 建议爪子 ID `10` 安全范围为 `[200, 700]`。因此新应用默认建议使用更保守的打开值：

```text
(10, 200)
```

如果实测发现 `200` 不够张开，再单独通过参数调整，不要写死。

建议参数：

```text
init_servo_1 := 500
init_servo_2 := 630
init_servo_3 := 151
init_servo_4 := 140
init_servo_5 := 500
gripper_open := 200
gripper_close := 560
```

### 10.2 跟踪

MVP 可以先只在夹取前把目标居中，不需要长期闭环。

参考策略：

- 根据目标中心相对画面中心的偏差调整舵机 `1` 和 `4`。
- 单次步长限制，例如最大 `10` PWM。
- 目标中心误差小于 `2%` 画面宽高时认为居中。

这部分必须有上限：

```text
max_tracking_seconds := 10
max_servo_step := 10
```

### 10.3 夹取

夹取流程建议：

1. 查询当前末端位姿 `/kinematics/get_current_pose`。
2. 根据深度和手眼矩阵计算目标机械臂坐标。
3. 如果距离超过 `max_distance_m`，返回 `TARGET_OUT_OF_RANGE`。
4. 调用 `/kinematics/set_pose_target` 获取目标脉宽。
5. 先转底座舵机 `1`。
6. 再移动 `2/3/4/5`。
7. 闭合爪子 `10`。
8. 抬高 `z + lift_height_m`。
9. 回到安全姿态。

建议参数：

```text
pick_pitch_near := 80
pick_pitch_far := 30
near_z_threshold_m := 0.2
lift_height_m := 0.10
```

如果 IK 没有返回 pulse：

```text
IK_FAILED
```

不能继续发布夹取舵机动作。

### 10.4 放置

MVP 可先提供固定放置序列，但必须参数化。

参考旧代码放置序列：

```text
(1, 500), (2, 535), (3, 170), (4, 220), (5, 500)
(1, 500), (2, 160), (3, 400), (4, 350), (5, 500)
open gripper
(1, 500), (2, 635), (3, 120), (4, 140), (5, 500)
```

新应用里建议把这些放到参数或配置文件，避免散落在代码里。

---

## 11. 状态机

建议状态：

```text
IDLE
  -> CHECK_READY
  -> LOAD_COLOR_CONFIG
  -> WAIT_CAMERA_FRAME
  -> INIT_POSE
  -> DETECT_TARGET
  -> TRACK_UNTIL_STABLE
  -> ESTIMATE_3D_POSITION
  -> SOLVE_IK
  -> EXECUTE_PICK
  -> LIFT_AND_HOME
  -> OPTIONAL_PLACE
  -> DONE
```

错误路径：

```text
ERROR
  -> STOP_MOTION
  -> REPORT_JSON
  -> EXIT_NON_ZERO
```

状态机必须由新节点自己维护，不要通过 `/claw_track_and_grab/pick_status` 这类旧服务维护。

---

## 12. 安全约束

MVP 必须满足：

1. 不发布 `/controller/cmd_vel`。
2. 不调用 `/claw_track_and_grab/*` 服务。
3. 不要求 `/claw_track_and_grab` 节点运行。
4. 不修改 `openclaw_controller` 源码。
5. 不修改 ROS2 上游、vendor driver、AgenticOS Runtime 或 Agentic Apps。
6. `--dry-run` 不发布任何舵机运动。
7. 未收到 RGB-D 图像时不运动。
8. 颜色配置缺失时不运动。
9. 目标深度无效时不运动。
10. IK 失败时不运动。
11. 超时时调用本节点 `stop()`，停止后续动作。
12. 爪子开合值默认遵守 `[200, 700]`，除非用户显式参数覆盖。

夹取前建议退出其他会控制机械臂、底盘或相机的 app：

```bash
ros2 service call /object_tracking/exit std_srvs/srv/Trigger "{}"
ros2 service call /line_following/exit std_srvs/srv/Trigger "{}"
ros2 service call /lidar_app/exit std_srvs/srv/Trigger "{}"
```

如果手机端正在手动控制机械臂，不要同时运行自动夹取。

---

## 13. 错误码

建议统一输出：

| 错误码 | 含义 |
| --- | --- |
| `OK` | 成功 |
| `INVALID_ARGUMENT` | CLI 参数错误 |
| `INVALID_COLOR` | 颜色不存在或 LAB 配置缺失 |
| `CAMERA_UNAVAILABLE` | RGB-D 话题不可用或没有帧 |
| `KINEMATICS_UNAVAILABLE` | kinematics 服务不可用 |
| `SERVO_CONTROLLER_UNAVAILABLE` | 舵机控制不可用 |
| `TARGET_NOT_FOUND` | 超时未检测到目标 |
| `TARGET_NOT_STABLE` | 目标无法稳定 |
| `DEPTH_INVALID` | 深度 ROI 无有效值 |
| `TARGET_OUT_OF_RANGE` | 目标超出夹取范围 |
| `IK_FAILED` | 逆解失败 |
| `MOTION_TIMEOUT` | 运动阶段超时 |
| `PICK_TIMEOUT` | 总抓取超时 |
| `STOPPED` | 用户或异常停止 |
| `UNKNOWN_ERROR` | 未分类异常 |

成功输出示例：

```json
{
  "ok": true,
  "error_code": "OK",
  "color": "red",
  "final_state": "DONE",
  "target_position_m": [0.18, 0.02, 0.04],
  "place_after_pick": false
}
```

失败输出示例：

```json
{
  "ok": false,
  "error_code": "DEPTH_INVALID",
  "color": "red",
  "final_state": "ESTIMATE_3D_POSITION"
}
```

---

## 14. 构建与测试

### 14.1 构建

```bash
source /home/ubuntu/ros2_ws/.robotrc
cd /home/ubuntu/ros2_ws
colcon build --symlink-install --packages-select color_block_grasper
source install/setup.bash
```

如果使用 zsh：

```bash
source install/setup.zsh
```

### 14.2 静态检查

```bash
cd /home/ubuntu/ros2_ws
python -m compileall src/color_block_grasper/color_block_grasper
```

### 14.3 单元测试

至少测试：

```bash
cd /home/ubuntu/ros2_ws
pytest -q src/color_block_grasper/test
```

测试内容：

- `depth_pixel_to_camera()` 数学正确。
- 深度 ROI 能过滤 `0` 和超大值。
- 颜色配置缺失时返回 `INVALID_COLOR`。
- CLI 参数解析正确。
- `--dry-run` 不创建真实运动命令。

### 14.4 dry-run

```bash
ros2 run color_block_grasper color_block_grasp_cli --color red --dry-run
```

期望：

- 检查颜色配置。
- 检查相机话题是否存在。
- 检查 kinematics 服务是否存在。
- 检查 `/servo_controller` 是否有订阅方。
- 不发布任何舵机动作。

### 14.5 真实抓取测试

确认 RGB-D 相机：

```bash
ros2 topic list | grep depth_cam
ros2 topic hz /depth_cam/rgb0/image_raw
ros2 topic hz /depth_cam/depth0/image_raw
```

确认底层服务：

```bash
ros2 service list | grep kinematics
ros2 topic info /servo_controller
```

执行抓取：

```bash
ros2 run color_block_grasper color_block_grasp_cli --color red --timeout 45
```

抓取并放置：

```bash
ros2 run color_block_grasper color_block_grasp_cli --color red --timeout 45 --place
```

---

## 15. 验收标准

实现完成后应满足：

1. 新包只新增在 `/home/ubuntu/ros2_ws/src/color_block_grasper`。
2. 不修改 `/opt/ros/*`、ROS2 上游、vendor driver、AgenticOS Runtime、Agentic Apps。
3. 不修改现有 `openclaw_controller` 源码。
4. 不调用 `/claw_track_and_grab/*` 服务。
5. 不要求 `/claw_track_and_grab` 节点运行。
6. `colcon build --symlink-install --packages-select color_block_grasper` 通过。
7. `python -m compileall src/color_block_grasper/color_block_grasper` 通过。
8. 单元测试通过。
9. `--dry-run` 不触发机械臂运动。
10. 非法颜色返回 `INVALID_COLOR`。
11. 相机不可用返回 `CAMERA_UNAVAILABLE`。
12. IK 不可用返回 `KINEMATICS_UNAVAILABLE` 或 `IK_FAILED`。
13. 合法颜色方块在视野内时，能完成夹取。
14. `--place` 能完成放置。
15. 新包不发布 `/controller/cmd_vel`。
16. 必须完成真实硬件抓取验收：指定一种颜色方块，执行 CLI 后，方块被爪子夹住并提离桌面。
17. 如果真实抓取失败，必须继续调试，不能只提交“可运行但抓不起来”的版本。
18. 调试记录必须写入最终回复或测试日志，至少包含：测试颜色、方块初始位置、目标像素中心、估计深度、计算出的抓取坐标、IK 返回脉宽、爪子开合参数、失败现象、每次调整内容、最终成功命令。

### 15.1 真实硬件调试闭环

真实测试必须按闭环推进：

1. 先用 `--dry-run` 确认相机、颜色配置、kinematics、servo controller 都可用。
2. 放置一个目标颜色方块在机械臂有效夹取范围内，建议距离相机 / 爪子不要超过 `30cm`。
3. 执行真实抓取命令。
4. 如果没有识别到目标，调整 LAB 阈值、光照或目标选择策略。
5. 如果识别到了但深度不对，调整深度 ROI、无效深度过滤、深度补偿。
6. 如果机械臂落点偏移，调整 `hand2cam` 平移参数和抓取坐标补偿。
7. 如果爪子碰到但夹不住，调整 `gripper_open`、`gripper_close`、夹取高度和闭合时机。
8. 如果能夹住但抬起时掉落，调整闭合脉宽、抬升高度、抬升速度和等待时间。
9. 每次只改一类参数，记录改动和结果。
10. 直到方块被实际夹起并离开桌面，才算该目标完成。

---

## 16. 实现顺序：

1. 新增 ROS2 Python 包骨架。
2. 实现 `status.py` 错误码和 JSON 输出结构。
3. 实现 `color_config.py`。
4. 实现 `depth_geometry.py` 和单元测试。
5. 实现 `vision.py`。
6. 实现 `motion.py`。
7. 实现 `color_block_grasper_node.py` 状态机。
8. 实现 `color_block_grasp_cli.py`。
9. 实现 launch 文件。
10. 跑构建、静态检查、单元测试。
11. 做真实机器人 dry-run。
12. 做真实抓取测试。
13. 如果抓不起来，继续调参并记录每次失败现象和调整。
14. 直到至少完成一次真实成功夹取，再输出最终结果。

---

## 17. 参考文件

```text
/home/ubuntu/8.机械臂运动控制.pdf
/home/ubuntu/ros2_ws/src/openclaw_controller/openclaw_controller/claw_track_and_grab/claw_track_and_grab.py
/home/ubuntu/ros2_ws/src/example/example/rgbd_function/utils/pick_and_place.py
/home/ubuntu/ros2_ws/src/large_models_examples/large_models_examples/color_sorting/object_sorting.py
/home/ubuntu/ros2_ws/src/driver/kinematics/kinematics/kinematics_control.py
/home/ubuntu/ros2_ws/src/driver/kinematics/kinematics/search_kinematics_solutions_node.py
/home/ubuntu/software/lab_tool/lab_config.yaml
```
