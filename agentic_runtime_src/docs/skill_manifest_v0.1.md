# Skill Contract v0.1

All callable capabilities are skills.

System skills live in:

```text
agentic_runtime_src/system_skills/<skill_name>/SKILL.md
```

App skills live in:

```text
agentic_apps/<app_id>/skills/<skill_dir>/SKILL.md
```

Runtime reads only the fenced `json agentic-skill` block inside `SKILL.md`. Markdown prose is documentation for people and agents; it cannot change execution behavior.

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
    "type": "object"
  },
  "output_schema": {
    "type": "object"
  }
}
```

Required metadata fields:

- `schema_version`
- `name`
- `scope`
- `access`
- `implementation`
- `input_schema`
- `output_schema`

Supported implementation types:

- `python`
- `ros2_service`
- `ros2_action`
- `runtime_internal`

System skills are globally visible. App skills must be named `app.*`, are loaded from the current App directory, and cannot override system skills.

Every dangerous robot skill still passes through Runtime schema validation, permission checks, access checks, resource locks, safety checks, timeout/cancellation handling, syscall records, and audit logs before its implementation runs.
