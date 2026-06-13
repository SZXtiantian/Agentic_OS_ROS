import pytest

from agentic_runtime.errors import PermissionDeniedError
from agentic_runtime.permission_manager import PermissionManager
from agentic_runtime.types import AppManifest, SkillManifest


def make_app(permissions):
    return AppManifest("test_app", "0", "", "main:run", permissions, [])


def make_skill(required):
    return SkillManifest(
        name="robot.navigate_to",
        version="0",
        description="",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        permission_requirements=required,
        resource_requirements={"locks": []},
        safety_constraints={},
        timeout_s=1,
        retry_policy={"max_attempts": 0, "retry_on": []},
        backend={"type": "mock"},
        observability={"audit": True},
    )


def test_permission_allowed():
    PermissionManager().check(make_app(["robot.move"]), make_skill(["robot.move"]))


def test_permission_denied():
    with pytest.raises(PermissionDeniedError):
        PermissionManager().check(make_app([]), make_skill(["robot.move"]))
