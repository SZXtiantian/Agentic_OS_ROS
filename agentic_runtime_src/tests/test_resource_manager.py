import pytest

from agentic_runtime.errors import ResourceLockedError
from agentic_runtime.skill_executor.resource_manager import ResourceManager


def test_rejects_duplicate_lock_from_other_session():
    manager = ResourceManager()
    manager.acquire("base", "sess1", "call1")
    with pytest.raises(ResourceLockedError):
        manager.acquire("base", "sess2", "call2")


def test_release_by_session():
    manager = ResourceManager()
    manager.acquire("base", "sess1", "call1")
    manager.release_by_session("sess1")
    assert manager.snapshot() == {}


def test_stop_robot_not_modeled_as_normal_lock():
    manager = ResourceManager()
    manager.acquire("base", "sess1", "call1")
    assert "base" in manager.snapshot()
