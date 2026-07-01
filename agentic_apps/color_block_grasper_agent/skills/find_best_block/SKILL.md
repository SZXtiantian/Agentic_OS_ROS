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
    "type": "object",
    "properties": {
      "candidates": {
        "type": "array"
      }
    },
    "required": [
      "candidates"
    ]
  },
  "output_schema": {
    "type": "object",
    "required": [
      "success"
    ],
    "properties": {
      "success": {
        "type": "boolean"
      },
      "selected": {
        "type": "object"
      },
      "index": {
        "type": "integer"
      }
    }
  },
  "permission_requirements": [],
  "resource_requirements": {
    "locks": []
  },
  "safety_constraints": {},
  "timeout_s": 3,
  "observability": {
    "audit": true
  }
}
```

## Purpose

Select the strongest detected color block candidate for this app's grasping workflow.

## Usage

Call this skill as `app.find_best_block` from the current app session. It is not visible to other Agent Apps.

## Safety

This app skill only ranks already provided candidate data. Robot motion remains in system skills guarded by the Runtime.
