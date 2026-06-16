#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PROFILE = Path("/opt/agentic/etc/bridge_profiles/rosorin_arm_camera.yaml")
FORBIDDEN_BACKEND_TOKENS = (
    "left_down",
    "right_down",
    "pick",
    "place",
    "grab",
    "grasp",
    "hand",
    "claw",
    "catch",
)
MAX_GRIPPER_DELTA = 20


def main(argv: list[str]) -> int:
    profile_path = Path(argv[1]).expanduser() if len(argv) > 1 else DEFAULT_PROFILE
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    arm = profile.get("arm") or {}
    action_root = Path(arm.get("action_group_path") or "/home/ubuntu/software/arm_pc/ActionGroups")
    actions = arm.get("allowed_named_actions") or {}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for name, spec in sorted(actions.items()):
        if not isinstance(spec, dict):
            failures.append({"name": name, "error_code": "ARM_ACTION_SPEC_INVALID", "reason": "action spec must be object"})
            continue
        backend_action = str(spec.get("backend_action") or name)
        path = action_root / f"{backend_action}.d6a"
        result = _inspect_action_group(name, backend_action, path)
        results.append(result)
        if not result["safe"]:
            failures.append(result)

    report = {
        "success": not failures,
        "profile_path": str(profile_path),
        "action_group_path": str(action_root),
        "checked_count": len(results),
        "results": results,
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


def _inspect_action_group(name: str, backend_action: str, path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "backend_action": backend_action,
        "path": str(path),
        "exists": path.exists(),
        "safe": False,
        "error_code": "",
        "reason": "",
        "row_count": 0,
        "gripper_column": "",
        "gripper_delta": 0,
    }
    if any(token in backend_action.lower() for token in FORBIDDEN_BACKEND_TOKENS):
        result.update(
            {
                "error_code": "CAMERA_POSE_BACKEND_SEMANTICALLY_UNSAFE",
                "reason": f"backend action name is forbidden for camera pose allowlist: {backend_action}",
            }
        )
        return result
    if not path.exists():
        result.update({"error_code": "CAMERA_POSE_BACKEND_MISSING", "reason": f"action group file missing: {path}"})
        return result
    try:
        rows, columns = _read_action_group(path)
    except Exception as exc:
        result.update({"error_code": "CAMERA_POSE_BACKEND_READ_FAILED", "reason": str(exc)})
        return result
    result["row_count"] = len(rows)
    gripper_column = "Servo10" if "Servo10" in columns else "Servo6" if "Servo6" in columns else ""
    result["gripper_column"] = gripper_column
    if gripper_column:
        index = columns.index(gripper_column)
        values = [int(row[index]) for row in rows if row[index] is not None]
        delta = max(values) - min(values) if values else 0
        result["gripper_delta"] = delta
        if delta > MAX_GRIPPER_DELTA:
            result.update(
                {
                    "error_code": "CAMERA_POSE_BACKEND_OPERATES_GRIPPER",
                    "reason": f"{backend_action}.d6a changes {gripper_column} by {delta}, above {MAX_GRIPPER_DELTA}",
                }
            )
            return result
    result["safe"] = True
    return result


def _read_action_group(path: Path) -> tuple[list[tuple[Any, ...]], list[str]]:
    with sqlite3.connect(path) as con:
        columns = [row[1] for row in con.execute("pragma table_info(ActionGroup)").fetchall()]
        rows = con.execute("select * from ActionGroup order by [Index]").fetchall()
    if not columns:
        raise ValueError("ActionGroup table missing")
    if not rows:
        raise ValueError("ActionGroup table is empty")
    return rows, columns


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
