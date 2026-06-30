import re

from agentic_os.kernel.scheduler.errors import SCHEDULER_ERROR_CODES
from agentic_runtime.errors import PermissionDeniedError


def test_error_serialization():
    err = PermissionDeniedError("missing robot.move")
    data = err.to_dict()
    assert data["success"] is False
    assert data["error_code"] == "PERMISSION_DENIED"
    assert data["recoverable"] is True


def test_scheduler_error_registry_covers_scheduler_source(runtime_src):
    scheduler_root = runtime_src / "agentic_os" / "kernel" / "scheduler"
    pattern = re.compile(r"""["'](SCHEDULER_[A-Z0-9_]+)["']""")
    literal_codes: set[str] = set()
    for path in scheduler_root.glob("*.py"):
        literal_codes.update(pattern.findall(path.read_text(encoding="utf-8")))

    generated_codes = {
        "SCHEDULER_AGENT_EXITED",
        "SCHEDULER_AGENT_FAILED",
        "SCHEDULER_AGENT_CRASHED",
        "SCHEDULER_AGENT_KILLED",
        "SCHEDULER_AGENT_REAPED",
        "SCHEDULER_REUSE_CONFIDENCE_OK_FAILED",
        "SCHEDULER_REUSE_SCHEMA_OK_FAILED",
        "SCHEDULER_REUSE_SOURCE_REAL_OK_FAILED",
        "SCHEDULER_REUSE_TTL_OK_FAILED",
        "SCHEDULER_REUSE_WORLD_EPOCH_OK_FAILED",
    }

    missing = sorted((literal_codes | generated_codes) - SCHEDULER_ERROR_CODES)

    assert missing == []
