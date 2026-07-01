# Skills: system skills 和 app skills

Skill 是 Runtime 可调度的能力单元。它不是只有一份 Markdown：`SKILL.md` 是 contract，后端实现必须存在，或必须由 `implementation` 明确指向 Runtime/bridge 拥有的实现入口。

## System Skills

System skill 是 Runtime 提供给所有 App 使用的受控能力，位于：

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

System skill 的 `scope` 是 `system`。当前仓库中的 system skill 主要有两类后端：

| implementation.type | 后端归属 | 例子 |
| --- | --- | --- |
| `runtime_internal` | Runtime 内部 manager/adapter | `memory.remember`、`human.ask`、`report.say` |
| `ros2_service` / `ros2_action` | Agentic OS-owned ROS2 bridge | `robot.get_state`、`arm.move_named`、`manipulation.pick_color_block` |

系统级机器人动作必须通过 system skill 暴露，不能做成 generic tool，也不能让 App 直接调用 ROS2、Nav2、MoveIt 或硬件驱动。

一个 system skill contract 至少要说清：

- `name` 和 `scope`
- `implementation`
- `input_schema`
- `output_schema`
- `permission_requirements`
- `resource_requirements.locks`
- `safety_constraints`
- `timeout_s`
- `observability.audit`

## App Skills

App skill 是某个 App 私有的能力，只在当前 App session 内可见，位于：

```text
agentic_apps/<app_name>/skills/<skill_name>/
  SKILL.md
  impl.py
```

示例：

```text
agentic_apps/color_block_grasper_agent/skills/find_best_block/
  SKILL.md
  impl.py
```

`SKILL.md` 中声明：

```json
{
  "name": "app.find_best_block",
  "scope": "app",
  "implementation": {
    "type": "python",
    "entrypoint": "impl:run"
  }
}
```

`impl.py` 中提供真实后端：

```python
def run(args: dict, context=None) -> dict:
    candidates = args.get("candidates")
    ...
    return {"success": True, "selected": selected, "index": index}
```

`app.find_best_block` 只对检测候选结果打分，选择 confidence 高且更居中的积木。它不移动机器人，不需要资源锁，也不能替代 `perception.detect_color_block` 或 `manipulation.pick_color_block` 这样的 system skill。

## 选择哪一种

| 场景 | 使用 |
| --- | --- |
| 所有 App 都可能复用的机器人、感知、存储、human、memory、report 能力 | System skill |
| 需要 Runtime 权限、资源锁、安全守卫、audit 的真实动作 | System skill |
| 只服务单个 App 的纯业务逻辑、排序、格式化、候选选择 | App skill |
| 想绕过 Runtime 直接调用 ROS2/硬件 | 不允许 |

## 开发检查

新增 skill 时必须确认：

- `SKILL.md` 可以被 Runtime 解析。
- `implementation` 指向真实存在的 backend。
- 输入输出 schema 覆盖失败路径。
- 需要真实设备的 skill 声明资源锁和 safety constraints。
- App skill 的后端代码与 `SKILL.md` 放在同一 skill 目录，或明确记录 backend 归属。
