# world.resolve_place

```json agentic-skill
{
  "access": {
    "required": false
  },
  "implementation": {
    "bridge": "world_model",
    "client_method": "resolve_place",
    "service": "/agentic/world/resolve_place",
    "service_type": "agentic_msgs/srv/ResolvePlace",
    "type": "ros2_service"
  },
  "input_schema": {
    "properties": {
      "name": {
        "type": "string"
      }
    },
    "required": [
      "name"
    ],
    "type": "object"
  },
  "name": "world.resolve_place",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "error_code": {
        "type": "string"
      },
      "place": {
        "type": "object"
      },
      "success": {
        "type": "boolean"
      }
    },
    "required": [
      "success"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "world.read"
  ],
  "resource_requirements": {
    "locks": []
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": false,
    "require_estop_released": false,
    "require_known_place": false
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 10
}
```

## Purpose

Resolve a human-readable place name into a registered place.

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
