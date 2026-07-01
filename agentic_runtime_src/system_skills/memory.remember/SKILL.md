# memory.remember

```json agentic-skill
{
  "access": {
    "required": false
  },
  "implementation": {
    "operation": "memory.remember",
    "type": "runtime_internal"
  },
  "input_schema": {
    "properties": {
      "key": {
        "type": "string"
      },
      "value": {}
    },
    "required": [
      "key",
      "value"
    ],
    "type": "object"
  },
  "name": "memory.remember",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
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
    "memory.write"
  ],
  "resource_requirements": {
    "locks": []
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": false
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 3
}
```

## Purpose

Store app memory by key.

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
