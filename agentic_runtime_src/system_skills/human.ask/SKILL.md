# human.ask

```json agentic-skill
{
  "access": {
    "irreversible": true,
    "required": true,
    "resource_type": "human"
  },
  "implementation": {
    "audit_backend": "runtime_human_queue",
    "correlation_id_from_call": true,
    "operation": "human.ask",
    "type": "runtime_internal"
  },
  "input_schema": {
    "properties": {
      "options": {
        "type": "array"
      },
      "question": {
        "type": "string"
      },
      "require_confirmation": {
        "type": "boolean"
      },
      "timeout_s": {
        "type": "integer"
      }
    },
    "required": [
      "question"
    ],
    "type": "object"
  },
  "name": "human.ask",
  "observability": {
    "audit": true,
    "record_feedback": false,
    "record_result": true
  },
  "output_schema": {
    "properties": {
      "answer": {
        "type": "string"
      },
      "answered": {
        "type": "boolean"
      }
    },
    "required": [
      "answered",
      "answer"
    ],
    "type": "object"
  },
  "permission_requirements": [
    "human.ask"
  ],
  "resource_requirements": {
    "locks": []
  },
  "retry_policy": {
    "max_attempts": 0,
    "retry_on": []
  },
  "safety_constraints": {
    "allow_cancel": true
  },
  "schema_version": 1,
  "scope": "system",
  "timeout_s": 60
}
```

## Purpose

Ask a human for input or confirmation.

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
