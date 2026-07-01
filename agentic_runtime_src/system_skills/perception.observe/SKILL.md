# perception.observe

```json agentic-skill
{
  "access": {
    "irreversible": false,
    "required": true,
    "resource_type": "robot_sensor"
  },
  "implementation": {
    "bridge": "inspection_bridge_node",
    "client_defaults": {
      "target": "workspace",
      "timeout_s": 10
    },
    "client_method": "observe",
    "json_output_fields": {
      "evidence": "evidence_json"
    },
    "request_id_field": "request_id",
    "service": "/agentic/perception/observe",
    "service_type": "agentic_msgs/srv/Observe",
    "type": "ros2_service"
  },
  "input_schema": {
    "properties": {
      "target": {
        "type": "string"
      },
      "timeout_s": {
        "maximum": 10,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "target"
    ],
    "type": "object"
  },
  "name": "perception.observe",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "evidence": {
        "type": "object"
      },
      "evidence_path": {
        "type": "string"
      },
      "objects": {
        "type": "array"
      },
      "success": {
        "type": "boolean"
      },
      "summary": {
        "type": "string"
      }
    },
    "required": [
      "success",
      "summary"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "perception.observe"
  ],
  "resource_requirements": {
    "locks": [
      "camera"
    ]
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": true,
    "camera_target_allowlist": true,
    "max_duration_s": 10,
    "require_estop_released": false,
    "runtime_timeout_margin_s": 5
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 10
}
```

## Purpose

Observe a target through the AgenticOS camera bridge.

## Usage

Call this skill through the Agentic Runtime skill API. Agent Apps must not call ROS2, Nav2, MoveIt, robot topics, or vendor drivers directly.

## Inputs

The Runtime validates arguments against `input_schema` from the `agentic-skill` metadata block.

## Outputs

The Runtime normalizes provider responses against `output_schema` and returns a structured `SkillResult`.

## Safety

Permission checks, access checks, resource locks, safety checks, timeouts, cancellation, system call records, and audit logs are enforced by the Runtime before the implementation is invoked.

## Implementation

Execution is selected from `implementation.type`; Runtime dispatch must not route by skill name.
