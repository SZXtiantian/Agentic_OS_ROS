# robot.inspect_area

```json agentic-skill
{
  "access": {
    "irreversible": true,
    "required": true,
    "resource_type": "robot_sensor"
  },
  "implementation": {
    "bridge": "inspection_bridge_node",
    "client_defaults": {
      "timeout_s": 60
    },
    "client_method": "inspect_area",
    "json_output_fields": {
      "result": "result_json"
    },
    "request_id_field": "request_id",
    "service": "/agentic/perception/inspect_area",
    "service_type": "agentic_msgs/srv/InspectArea",
    "type": "ros2_service"
  },
  "input_schema": {
    "properties": {
      "place": {
        "type": "string"
      },
      "timeout_s": {
        "maximum": 120,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "place"
    ],
    "type": "object"
  },
  "name": "robot.inspect_area",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "anomalies": {
        "type": "array"
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
    "perception.inspect"
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
    "require_estop_released": false,
    "require_known_place": true,
    "runtime_timeout_margin_s": 5
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 60
}
```

## Purpose

Inspect a registered place and return a summary.

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
