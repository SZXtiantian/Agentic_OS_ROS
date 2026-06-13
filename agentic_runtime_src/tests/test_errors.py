from agentic_runtime.errors import PermissionDeniedError


def test_error_serialization():
    err = PermissionDeniedError("missing robot.move")
    data = err.to_dict()
    assert data["success"] is False
    assert data["error_code"] == "PERMISSION_DENIED"
    assert data["recoverable"] is True
