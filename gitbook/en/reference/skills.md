# Skills: System Skills and App Skills

A skill is a Runtime-dispatchable capability unit. It is not only a Markdown file. `SKILL.md` is the contract; the backend implementation must exist, or the `implementation` block must clearly point to a Runtime/bridge-owned implementation entry.

## System Skills

System skills are Runtime-provided controlled capabilities available to apps:

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

System skills use `scope: system`. The current repository mainly uses two backend types:

| implementation.type | Backend Owner | Examples |
| --- | --- | --- |
| `runtime_internal` | Runtime manager/adapter | `memory.remember`, `human.ask`, `report.say` |
| `ros2_service` / `ros2_action` | Agentic OS-owned ROS2 bridge | `robot.get_state`, `arm.move_named`, `manipulation.pick_color_block` |

System-level robot actions must be exposed as system skills. They must not be generic tools, and Agent Apps must not call ROS2, Nav2, MoveIt, or hardware drivers directly.

A system skill contract should define:

- `name` and `scope`
- `implementation`
- `input_schema`
- `output_schema`
- `permission_requirements`
- `resource_requirements.locks`
- `safety_constraints`
- `timeout_s`
- `observability.audit`

## App Skills

App skills are private to one app and visible only inside that app session:

```text
agentic_apps/<app_name>/skills/<skill_name>/
  SKILL.md
  impl.py
```

Example:

```text
agentic_apps/color_block_grasper_agent/skills/find_best_block/
  SKILL.md
  impl.py
```

`SKILL.md` declares:

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

`impl.py` provides the backend:

```python
def run(args: dict, context=None) -> dict:
    candidates = args.get("candidates")
    ...
    return {"success": True, "selected": selected, "index": index}
```

`app.find_best_block` scores detected candidates and selects the highest-confidence, most-centered block. It does not move the robot, does not need resource locks, and cannot replace system skills such as `perception.detect_color_block` or `manipulation.pick_color_block`.

## Which One to Use

| Scenario | Use |
| --- | --- |
| Robot, perception, storage, human, memory, or report capability shared by apps | System skill |
| Real action requiring Runtime permissions, resource locks, safety guards, and audit | System skill |
| App-private business logic, ranking, formatting, or candidate selection | App skill |
| Bypassing Runtime to call ROS2/hardware directly | Not allowed |

## Development Checks

When adding a skill, verify:

- `SKILL.md` can be parsed by Runtime.
- `implementation` points to a real backend.
- Input/output schemas cover failure paths.
- Skills using real devices declare resource locks and safety constraints.
- App skill backend code lives in the same skill directory, or backend ownership is explicitly documented.
