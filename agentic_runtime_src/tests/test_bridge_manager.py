from agentic_runtime.hardware_adapter import BridgeManager, Ros2BridgeProfile


def test_bridge_manager_status_and_mock_install(tmp_path):
    manager = BridgeManager(tmp_path / "bridges" / "ros2", tmp_path / "profiles")
    installed = manager.install_profile(Ros2BridgeProfile(name="ros2_mock"))
    status = manager.status()

    assert installed["status"] == "installed_mock_profile"
    assert status["installed"] is True
    assert status["metadata"]["profile"] == "ros2_mock"
