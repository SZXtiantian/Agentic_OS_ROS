# 纯 Skill 重构方案

## 目标

这次改造不是推倒 Agentic Runtime，也不是重写机器人控制逻辑。

目标是把开发者心智模型收敛成一句话：

```text
所有可调用能力都是 skill。
系统提供 system skills。
应用可以带 app skills。
```

开发者只需要理解这三类目录：

```text
agentic_apps/<app>/main.py             App 流程
agentic_apps/<app>/skills/             App 自带能力，也就是 app skills
agentic_runtime_src/system_skills/     系统自带能力，也就是 system skills
```

面向开发者的新设计里，不再要求开发者理解旧中间层、旧总包、旧运行脚本命名。开发者写 App 时只需要写流程和 skill。

## 关键决定

### 1. 不叫 local skills

应用自带能力统一叫：

```text
app skills
```

不用 `local skills` 这个名字，因为它表达的是“位置”，不是“归属”。开发者真正关心的是：这个 skill 属于当前 App，只在当前 App 里可见。

命名规则：

```text
system skill: robot.get_state
system skill: perception.detect_color_block
system skill: manipulation.pick_color_block

app skill: app.find_best_block
app skill: app.plan_pick_sequence
app skill: app.select_target_pose
```

Runtime 解析规则：

- system skills 全局可见。
- app skills 只在当前 App/session 可见。
- app skills 不能覆盖 system skills。
- app skills 名字必须以 `app.` 开头。

### 2. Skill 文件使用 Markdown

新 skill 格式统一使用：

```text
SKILL.md
```

这里先给出明确的定义：

```text
Skill = 一个可调用能力包。
SKILL.md = 这个能力的说明书 + 机器可读契约。
```

也就是说，`SKILL.md` 不是纯自然语言文档，也不是纯配置文件。它必须同时服务两类读者：

```text
开发者和 Agent 读取说明书部分，用来理解这个能力怎么用、怎么改、有什么边界。
Runtime 读取机器可读契约部分，用来校验、授权、加锁、安全检查、审计和分发执行。
```

不使用新的 `skill.yaml`。

原因很简单：这里的目标是让开发者更容易上手和 DIY。Skill 不是纯机器配置，它同时包含：

- 这个能力是干什么的
- 什么时候应该用
- 输入参数怎么写
- 输出结果怎么看
- 安全边界是什么
- 如何调用这个能力
- 怎么修改或替换实现
- 具体怎么实现

如果用 YAML，开发者通常还要再写一份说明文档。用 `SKILL.md` 可以把“人看的说明”和“机器读取的契约”放在一个文件里。

`SKILL.md` 的结构分成两部分：

```text
能力说明书：
- 功能说明
- 使用场景
- 输入参数说明
- 输出结果说明
- 调用示例
- 安全注意事项
- DIY/修改指南

机器可读契约：
- name
- scope: system / app
- access
- implementation
- input_schema
- output_schema
- timeout
- observability
```

机器可读契约不靠自然语言猜。`SKILL.md` 里必须有一个严格 JSON 元数据块：

````markdown
# perception.detect_color_block

```json agentic-skill
{
  "schema_version": 1,
  "name": "perception.detect_color_block",
  "scope": "system",
  "access": {
    "required": true,
    "resource_type": "robot_sensor",
    "irreversible": false
  },
  "implementation": {
    "type": "ros2_service",
    "service": "/agentic/perception/detect_color_block",
    "service_type": "agentic_msgs/srv/DetectColorBlock"
  },
  "input_schema": {
    "type": "object",
    "properties": {
      "color": { "type": "string" }
    },
    "required": ["color"]
  },
  "output_schema": {
    "type": "object"
  }
}
```

## 功能说明

检测指定颜色的色块。

## 调用示例

```python
await ctx.kernel.skill.call("perception.detect_color_block", {"color": "red"})
```
````

这个方案比 YAML 更适合开发者，同时仍然保持机器可验证：

- Markdown 正文负责能力说明书。
- `json agentic-skill` 代码块负责机器可读契约。
- Runtime 用 Markdown parser 找到 `agentic-skill` 代码块，再用 JSON parser 解析。
- Runtime 只相信 JSON 契约，不从普通说明文字里猜字段。
- 自然语言说明可以帮助开发者和 Agent 理解，但不能改变 Runtime 执行行为。

## 保留什么

这些 Runtime 设计继续保留，不要重写：

- `agentic_runtime_src/agentic_runtime/skill_executor/`
- `agentic_runtime_src/agentic_runtime/skill_registry/`
- `agentic_runtime_src/agentic_runtime/sdk/`
- `agentic_runtime_src/agentic_runtime/kernel_service/`
- 权限检查
- 资源锁
- 安全检查
- 审计日志
- 结构化错误码
- Agent App 通过 `ctx.kernel.skill.call(...)` 或 SDK 高层 API 调用能力

`skill_executor/` 要保留，但它保留的是 Runtime 执行边界，不是现在这种实现形态。

当前 `skill_executor/` 的问题是：权限、安全、锁、审计这些正确职责，和按 skill 名字硬编码路由的错误实现混在一起了。重构时要保留前者，删除后者。

`skill_executor/` 应该继续负责：

- 入参 schema 校验
- 权限检查
- 访问权限检查
- 安全检查
- 资源锁
- 超时和取消逻辑
- 系统调用记录
- 审计日志
- 统一的 `SkillResult` 归一化

`skill_executor/` 不应该继续保留：

- `dispatcher.py` 里按 skill 名字逐个 `if` 的路由
- `dispatcher.py` 里直接绑定某一个机器人传输客户端
- `executor.py` 里按 skill 名字硬编码访问规则
- `executor.py` 里按 skill 名字硬编码人工介入规则
- `dispatcher.py` 里混入某个具体 App 的存储逻辑
- skill 已经迁移到 `implementation` 之后还继续读取 `skill.backend`

现有 App 主流程也保留，例如：

```text
agentic_apps/color_block_grasper_agent/main.py
```

该文件可以继续调用系统 skill：

```python
await ctx.kernel.skill.call("perception.detect_color_block", {...})
await ctx.kernel.skill.call("manipulation.pick_color_block", {...})
```

也可以调用当前 App 自己的 app skill：

```python
await ctx.kernel.skill.call("app.find_best_block", {...})
```

## 新增什么

新增系统 skill 目录：

```text
agentic_runtime_src/system_skills/
```

一个系统能力一个目录：

```text
agentic_runtime_src/system_skills/
  robot.get_state/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  robot.stop/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  arm.get_state/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  arm.move_named/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  gripper.set/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  perception.capture_photo/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  perception.detect_color_block/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  perception.center_color_block/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  perception.verify_held_color_block/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  manipulation.pick_color_block/
    SKILL.md
    impl.py
    ros_node.py
    tests/

  manipulation.place_color_block/
    SKILL.md
    impl.py
    ros_node.py
    tests/
```

新增 App skill 支持：

```text
agentic_apps/<app_name>/skills/<skill_name>/
  SKILL.md
  impl.py
  tests/
```

例子：

```text
agentic_apps/color_block_grasper_agent/skills/find_best_block/
  SKILL.md
  impl.py
  tests/
```

App skill 的 `SKILL.md` 示例：

````markdown
# app.find_best_block

```json agentic-skill
{
  "schema_version": 1,
  "name": "app.find_best_block",
  "scope": "app",
  "access": {
    "required": false
  },
  "implementation": {
    "type": "python",
    "entrypoint": "impl:run"
  },
  "input_schema": {
    "type": "object"
  },
  "output_schema": {
    "type": "object"
  }
}
```

## 功能说明

从候选检测结果里选择最适合抓取的色块。
````

新增统一 skill 运行时：

```text
agentic_runtime_src/agentic_runtime/skill_runtime/
  python_runner.py
  ros2_service_runner.py
  ros2_action_runner.py
  result.py
```

`skill_runtime/` 的职责：

- 根据 `SKILL.md` 中 JSON 元数据块的 `implementation.type` 选择执行器。
- 支持 `python`、`ros2_service`、`ros2_action`。
- 返回统一 `SkillResult`。
- 不做权限、安全、锁、审计；这些仍然由 `skill_executor/` 负责。

## 迁移什么

### 1. 系统 skill

把当前系统能力定义迁移到：

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

例如：

```text
agentic_runtime_src/system_skills/perception.detect_color_block/SKILL.md
```

旧的能力定义文件只作为一次性迁移输入。迁移完成后，新 skill 不再使用 YAML 文件作为 skill 格式。

旧字段迁移规则：

```text
backend -> implementation
```

### 2. ROS2 节点源码

当前 ROS2 适配源码只作为迁移源。目标状态不要把它保留成一个开发者要理解的概念。

把现有 ROS2 节点按 skill 拆到对应目录：

```text
状态读取逻辑
-> system_skills/robot.get_state/ros_node.py

拍照逻辑
-> system_skills/perception.capture_photo/ros_node.py

目标检测逻辑
-> system_skills/perception.detect_color_block/ros_node.py

目标居中逻辑
-> system_skills/perception.center_color_block/ros_node.py

抓取后验证逻辑
-> system_skills/perception.verify_held_color_block/ros_node.py

机械臂状态逻辑
-> system_skills/arm.get_state/ros_node.py

机械臂预设动作逻辑
-> system_skills/arm.move_named/ros_node.py

夹爪控制逻辑
-> system_skills/gripper.set/ros_node.py

抓取逻辑
-> system_skills/manipulation.pick_color_block/ros_node.py

放置逻辑
-> system_skills/manipulation.place_color_block/ros_node.py
```

ROS2 message、service、action 定义放到：

```text
agentic_runtime_src/system_skills/interfaces/
  msg/
  srv/
  action/
  CMakeLists.txt
  package.xml
```

这个目录只是 system skills 的实现支撑，不是新的开发者层级。

### 3. Runtime 客户端命名

把 Runtime 内部旧的 ROS2 客户端包整体替换为：

```text
agentic_runtime_src/agentic_runtime/skill_runtime/
```

新代码统一使用这些名字：

```text
Ros2SkillRuntimeClient
SkillRuntimeCommandError
create_skill_runtime_client
```

Runtime 配置字段统一使用：

```text
skill_provider_transport
skill_provider_root
robot_profile_root
```

机器人配置目录统一使用：

```text
agentic_runtime_src/configs/robot_profiles/
/opt/agentic/etc/robot_profiles/
```

### 4. 脚本

脚本统一改成 skill 语义。旧的构建、运行、启动脚本迁移后只保留这些用户可见名字：

```text
agentic_runtime_src/scripts/run_system_skill_nodes.sh
agentic_runtime_src/scripts/build_system_skill_nodes.sh
agentic_runtime_src/scripts/run_robot_skills.sh
```

脚本内部仍然可以 source ROS2 setup 文件，但脚本名、日志、帮助信息都应该使用 system skill nodes 或 robot skills 的说法。

### 5. App skills

App skills 不要求开发者再去某个 YAML 文件里登记。

默认发现规则：

```text
agentic_apps/<app_name>/skills/*/SKILL.md
```

Runtime 加载规则：

- 先加载 system skills。
- 再扫描并加载当前 App 的 app skills。
- app skill 名字必须以 `app.` 开头。
- app skill 只在当前 App/session 可见。
- app skill 不能覆盖 system skill。

## 删除什么

迁移完成后，删除或退役这些旧源码概念：

```text
旧 ROS2 适配源码总目录
旧 Runtime ROS2 客户端包
旧机器人配置目录
旧 YAML skill 格式
```

源码迁移完成后，可以清理生成产物：

```text
build/
install/
log/
```

不要手动修改生成产物来伪装完成迁移。

旧文档要重写或删除，尤其是主要解释旧中间层模型、旧文件布局、旧 provider 协议的文档。

替换成下面这些主题的文档：

- system skills
- app skills
- `SKILL.md` 格式
- skill implementation types
- 基于 ROS2 的 system skill nodes
- 安全和审计边界

## 哪里不能改

不要修改：

```text
/opt/ros/*
/home/ubuntu/ros2_ws/src
ROS2 上游源码
Nav2 上游源码
MoveIt 上游源码
机器人厂商驱动源码
```

不要把 Agentic Runtime 放进 ROS2，当成普通 ROS2 业务节点运行。

Agent Apps 里不允许出现这些 import 或直接机器人调用：

```text
import rclpy
from rclpy ...
/cmd_vel
/scan
/odom
/tf
直接调用 Nav2 action
直接调用 MoveIt action
```

普通 app skills 默认也不允许 import `rclpy`。

只有 system skill 的 ROS2 节点文件可以 import `rclpy`，并且必须放在：

```text
agentic_runtime_src/system_skills/<system_skill>/ros_node.py
agentic_runtime_src/system_skills/interfaces/
```

不要绕过 Runtime 检查。危险机器人动作仍然必须经过：

```text
入参 schema 校验
权限检查
访问权限检查
资源锁
安全检查
超时
取消
审计日志
结构化错误码
```

## Runtime 修改点

### 1. Skill 文档解析

新增或修改：

```text
agentic_runtime_src/agentic_runtime/skill_registry/
```

要求：

- 读取 `SKILL.md`。
- 找到语言标记为 `json agentic-skill` 的代码块。
- 用 JSON parser 解析该代码块。
- 校验必填字段：`schema_version`、`name`、`scope`、`implementation`、`input_schema`、`output_schema`。
- 不从普通 Markdown 正文里猜字段。
- 新 skill 不允许使用 `skill.yaml`。

内部类型可以继续叫 `SkillManifest`，这样代码迁移成本低；但面向开发者的文件格式叫 `SKILL.md`。

### 2. SkillExecutor 边界

修改：

```text
agentic_runtime_src/agentic_runtime/skill_executor/executor.py
```

当前问题：

`SkillExecutor` 看起来是通用 skill executor，但关键决策仍然按 skill 名字硬编码：

- `_requires_access_check(skill.name)`
- `_access_resource_type(skill.name)`
- `_requires_intervention(skill.name)`
- 通过 dispatcher 上的旧传输客户端调用安全检查
- `backend_name = skill.backend.get("type", ...)`

要求改成：

- 用 `SKILL.md` 元数据替代硬编码访问规则和人工介入规则。
- 资源类型从 `access.resource_type` 读取，不从 skill 名字推断。
- 人工介入风险从 `access.irreversible` 读取，不从 skill 名字推断。
- 读取 `implementation`，不再读取 `backend`。
- 调用通用 skill 运行时执行已经解析好的 skill 和参数。
- 继续保留已有权限检查、安全检查、资源锁、超时、系统调用记录、审计保证。

危险运动类 skill 示例：

````markdown
```json agentic-skill
{
  "schema_version": 1,
  "name": "manipulation.pick_color_block",
  "scope": "system",
  "access": {
    "required": true,
    "resource_type": "robot_motion",
    "irreversible": true
  },
  "implementation": {
    "type": "ros2_action",
    "action": "/agentic/manipulation/pick_color_block",
    "action_type": "agentic_msgs/action/PickColorBlock"
  },
  "input_schema": { "type": "object" },
  "output_schema": { "type": "object" }
}
```
````

### 3. SkillDispatcher 替换方式

修改：

```text
agentic_runtime_src/agentic_runtime/skill_executor/dispatcher.py
```

当前问题：

`dispatcher.py` 现在是一个手写路由表：

```python
if skill_name == "robot.get_state":
    ...
if skill_name == "perception.detect_color_block":
    ...
if skill_name == "manipulation.pick_color_block":
    ...
```

这会导致两个问题：

- app skills 无法自然接入。
- 每新增一个 system skill 都要改 Runtime 代码。

要求改成：

- 用 `implementation.type` 分发，不按 skill 名字分发。
- Dispatcher 接收已经解析好的 skill 对象，不只接收 `skill_name`。
- Dispatcher 根据 `implementation.type` 选择执行器。
- memory、human、report、storage 这类 Runtime 内部能力，要么变成一等 skill 实现方式，要么变成专门的 Runtime 实现类型，不要继续塞进一个巨大分支文件。

目标调用形态：

```python
raw = await self.dispatcher.dispatch(
    skill=skill,
    args=args,
    app_id=app.name,
    session_id=session_id,
    cancel_event=cancel_event,
    call_id=call.call_id,
)
```

Dispatcher 内部形态：

```python
implementation_type = skill.implementation["type"]
runner = self.runners[implementation_type]
return await runner.run(skill, args, context)
```

这次重构期间不要新增按 skill 名字判断的新分支。

### 4. SkillRegistry

修改：

```text
agentic_runtime_src/agentic_runtime/skill_registry/registry.py
```

要求：

- 从 `agentic_runtime_src/system_skills/*/SKILL.md` 加载 system skills。
- 迁移期间可以临时兼容旧能力定义文件，但新 skill 只能用 `SKILL.md`。
- 从 `agentic_apps/<app>/skills/*/SKILL.md` 加载 app skills。
- 拒绝不以 `app.` 开头的 app skill 名字。
- 拒绝逃逸出当前 App 目录的 app skill 路径。
- 拒绝 app skill 覆盖 system skill。

### 5. AppManager

修改：

```text
agentic_runtime_src/agentic_runtime/app_manager/app_manager.py
```

要求：

- 运行 App 时扫描该 App 的 `skills/*/SKILL.md`。
- 把 App skill overlay 接入 skill executor 或 registry 解析路径。
- app skill 可见性必须限制在当前 App/session。
- 不要求开发者额外维护 skill 列表。

## 测试计划

新增或更新这些测试：

- 从 `system_skills/` 加载 `SKILL.md`。
- 从 `agentic_apps/<app>/skills/` 加载 app skill。
- `SKILL.md` 缺少 `json agentic-skill` 块时报结构化错误。
- `SKILL.md` 里的 JSON 元数据非法时报结构化错误。
- Runtime 只解析 `json agentic-skill` 契约块，不从 Markdown 正文推断执行字段。
- 修改 Markdown 正文说明不应该改变 skill 的 Runtime 契约。
- 新 skill 不允许使用 `skill.yaml`。
- 迁移期间旧能力定义文件仍能临时加载。
- 拒绝 app skill 路径逃逸。
- app skill 不能覆盖 system skill。
- app skill 必须以 `app.` 开头。
- 普通 Agent App 仍然不能 import `rclpy`。
- 普通 app skill 不能 import `rclpy`。
- system skill 的 `ros_node.py` 可以 import `rclpy`。
- 危险动作仍然要求权限检查、锁、安全检查、审计。
- 迁移完成后，旧的用户可见命令名不再出现在文档和脚本里。

至少运行：

```bash
cd /home/ubuntu/Agentic_OS_ROS_publish
PYTHONPATH=agentic_runtime_src pytest -q agentic_runtime_src/tests agentic_apps/color_block_grasper_agent/tests
scripts/run_tests.sh
```

如果改到了基于 ROS2 的 system skill nodes，再运行：

```bash
source /opt/ros/humble/setup.bash
cd /home/ubuntu/Agentic_OS_ROS_publish
colcon build --symlink-install
```

## 实现顺序

1. 新增 `system_skills/`，把现有系统能力迁移成一个 skill 一个目录的 `SKILL.md` 布局。
2. 给 registry 增加 `SKILL.md` 解析。
3. 给 registry 增加 system skill 目录加载，同时保留旧能力定义文件临时兼容。
4. 增加 app skills 自动扫描和 App/session 作用域隔离。
5. 新增 `skill_runtime/`，实现 Python、ROS2 service、ROS2 action 执行器。
6. 把 Runtime 内部旧客户端逻辑迁移到 `skill_runtime/`。
7. 配置字段改名，同时保留旧字段临时别名。
8. 按 skill 拆分 ROS2 节点源码。
9. 重命名脚本。
10. 更新测试。
11. 更新文档，移除旧的用户可见术语。
12. 测试通过后，再删除退役源码目录和旧 YAML skill 格式。

## Codex 目标命令

可以把下面这段直接发给 Codex 执行：

```text
/goal 在 /home/ubuntu/Agentic_OS_ROS_publish 实现 SKILL_ONLY_REFACTOR_PLAN.md 里的纯 Skill 重构。保留 Runtime 的权限检查、资源锁、安全检查、审计日志、结构化错误码，以及 Agent App 不能直接碰 ROS2 的边界。新增 system_skills 一 skill 一目录布局；每个 skill 是一个可调用能力包，每个 SKILL.md 都是能力说明书 + 机器可读契约。SKILL.md 内必须包含 json agentic-skill 元数据块，Runtime 只解析这个契约块，不从 Markdown 正文推断执行字段；不使用新的 skill.yaml。新增 app skills，App skill 名字使用 app.*，从 agentic_apps/<app>/skills/*/SKILL.md 自动扫描并限制在当前 App/session 可见。新增 skill_runtime 执行器，按 implementation.type 分发，不再按 skill 名字硬编码路由。完成配置、脚本、文档、测试更新，并在兼容测试通过后移除退役的用户可见中间层术语和旧 YAML skill 格式。不要修改 /opt/ros、ROS2/Nav2/MoveIt 上游源码、机器人厂商驱动源码、/home/ubuntu/ros2_ws/src。运行 PYTHONPATH=agentic_runtime_src pytest -q agentic_runtime_src/tests agentic_apps/color_block_grasper_agent/tests 和 scripts/run_tests.sh，最后报告修改文件、执行命令、测试结果、剩余风险、下一步。
```
