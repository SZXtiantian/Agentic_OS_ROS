import asyncio
import subprocess
from pathlib import Path

import yaml

import agentic_runtime.hardware_adapter.installer as installer_module
from agentic_runtime.hardware_adapter import BridgeInstaller, BridgeManager, Ros2BridgeProfile, RosBridgeClientTransport
from agentic_runtime.hardware_adapter.installer import DEFAULT_BRIDGE_PACKAGES


def _bridge_workspace(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "agentic_ws" / "ros2_bridge_src"
    for package in DEFAULT_BRIDGE_PACKAGES:
        package_root = source / package
        package_root.mkdir(parents=True)
        (package_root / "package.xml").write_text(f"<package><name>{package}</name></package>", encoding="utf-8")
    ros_setup = tmp_path / "opt" / "ros" / "humble" / "setup.bash"
    ros_setup.parent.mkdir(parents=True)
    ros_setup.write_text("# fake setup\n", encoding="utf-8")
    return source, ros_setup


def test_bridge_installer_plan_lists_commands_without_running(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)

    installer = BridgeInstaller(source, tmp_path / "bridges" / "ros2", ros_setup_path=ros_setup)

    plan = installer.plan()

    assert plan["implemented"] is True
    assert plan["safe_to_run"] is True
    assert plan["missing_packages"] == []
    assert plan["packages"] == sorted(DEFAULT_BRIDGE_PACKAGES)
    assert plan["commands"][0] == f"source {ros_setup}"
    assert "colcon --log-base log/ros2_bridge build" in plan["commands"][2]


def test_bridge_installer_lifecycle_methods_are_dry_run_safe(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)
    installer = BridgeInstaller(source, tmp_path / "bridges" / "ros2", ros_setup_path=ros_setup)

    assert installer.validate()["success"] is True
    assert installer.build_workspace(dry_run=True)["status"] == "install_planned"
    assert installer.activate()["status"] == "active"
    assert installer.status()["status"] == "active"
    assert installer.rollback()["status"] == "rolled_back"
    assert installer.status()["status"] == "rolled_back"


def test_bridge_installer_install_dry_run_does_not_subprocess(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)

    def runner(command, timeout_s):
        raise AssertionError(f"dry-run should not execute {command} with timeout {timeout_s}")

    installer = BridgeInstaller(source, tmp_path / "bridges" / "ros2", ros_setup_path=ros_setup, command_runner=runner)

    result = installer.install(dry_run=True)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["installed"] is False
    assert not (tmp_path / "bridges" / "ros2" / "status.json").exists()


def test_bridge_installer_requires_env_for_real_install(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.delenv("AGENTIC_ALLOW_BRIDGE_INSTALL", raising=False)
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)

    def runner(command, timeout_s):
        raise AssertionError("install must be blocked before subprocess")

    installer = BridgeInstaller(source, tmp_path / "bridges" / "ros2", ros_setup_path=ros_setup, command_runner=runner)

    result = installer.install(dry_run=False)

    assert result["success"] is False
    assert result["error_code"] == "BRIDGE_INSTALL_REQUIRES_OPT_IN"
    assert result["installed"] is False


def test_bridge_installer_real_install_writes_status_when_opted_in(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.setenv("AGENTIC_ALLOW_BRIDGE_INSTALL", "1")
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)

    def runner(command, timeout_s):
        assert command[:2] == ["bash", "-lc"]
        assert timeout_s == 900
        return subprocess.CompletedProcess(command, 0, stdout="built\n", stderr="")

    installer = BridgeInstaller(source, tmp_path / "bridges" / "ros2", ros_setup_path=ros_setup, command_runner=runner)

    result = installer.install(dry_run=False)

    assert result["success"] is True
    assert result["installed"] is True
    assert result["status"] == "installed"
    assert (tmp_path / "bridges" / "ros2" / "status.json").exists()


def test_bridge_manager_install_profile_records_real_metadata(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)
    manager = BridgeManager(
        tmp_path / "bridges" / "ros2",
        tmp_path / "profiles",
        installer_kwargs={"ros_setup_path": ros_setup},
    )
    profile = Ros2BridgeProfile(
        name="ros2_default",
        source_workspace=str(source),
        capabilities=[
            {
                "name": "robot.navigate_to",
                "ros2_interface": {
                    "kind": "action",
                    "name": "/navigate_to_pose",
                    "type": "nav2_msgs/action/NavigateToPose",
                },
            }
        ],
        safety={"require_estop_released": True, "require_localized": True},
    )
    installed = manager.install_profile(profile, dry_run=True)
    status = manager.status()
    profile_path = tmp_path / "profiles" / "ros2_default.yaml"
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert installed["status"] == "installed_profile"
    assert installed["dry_run"] is True
    assert installed["ros_distro"] == "humble"
    assert installed["bridge_endpoint"] == "ros2-cli://agentic-bridge"
    assert "ros2 node list" in installed["health_check_command"]
    assert status["installed"] is True
    assert status["metadata"]["profile"] == "ros2_default"
    assert status["metadata"]["source_workspace"] == str(source)
    assert payload["status"] == "installed_profile"
    assert payload["installed_root"] == str(tmp_path / "bridges" / "ros2")
    assert payload["safety"]["require_localized"] is True
    assert payload["capabilities"][0]["name"] == "robot.navigate_to"


def test_bridge_manager_lifecycle_plan_validate_activate_rollback(tmp_path, monkeypatch):
    source, ros_setup = _bridge_workspace(tmp_path)
    monkeypatch.setattr(installer_module.shutil, "which", lambda name: "/usr/bin/colcon" if name == "colcon" else None)
    manager = BridgeManager(
        tmp_path / "bridges" / "ros2",
        tmp_path / "profiles",
        installer_kwargs={"ros_setup_path": ros_setup},
    )
    profile = Ros2BridgeProfile(name="ros2_default", source_workspace=str(source))

    assert manager.plan(profile)["safe_to_run"] is True
    assert manager.validate(profile)["success"] is True
    assert manager.build_workspace(profile, dry_run=True)["status"] == "install_planned"
    assert manager.activate(profile)["status"] == "active"
    assert manager.status()["metadata"]["status"] == "active"
    assert manager.rollback(profile)["status"] == "rolled_back"
    assert manager.status()["metadata"]["status"] == "rolled_back"


def test_bridge_manager_rejects_malformed_install_result(tmp_path):
    class MalformedInstaller:
        def install(self, dry_run=True):
            return {"success": "false", "plan": {}}

    manager = BridgeManager(tmp_path / "bridges" / "ros2", tmp_path / "profiles")
    manager._installer = lambda profile: MalformedInstaller()
    profile = Ros2BridgeProfile(name="ros2_default", source_workspace=str(tmp_path / "src"))

    result = manager.install_profile(profile, dry_run=True)

    assert result["success"] is False
    assert result["error_code"] == "BRIDGE_INSTALL_RESULT_INVALID"
    assert not (tmp_path / "bridges" / "ros2" / "status.json").exists()


def test_bridge_manager_rejects_malformed_lifecycle_result(tmp_path):
    class MalformedInstaller:
        def activate(self):
            return {"success": "false", "reason": "string success"}

        def rollback(self):
            return {"success": False, "reason": "missing code"}

    manager = BridgeManager(tmp_path / "bridges" / "ros2", tmp_path / "profiles")
    manager._installer = lambda profile: MalformedInstaller()
    profile = Ros2BridgeProfile(name="ros2_default", source_workspace=str(tmp_path / "src"))

    activated = manager.activate(profile)
    status_after_activate = manager.status()
    rolled_back = manager.rollback(profile)
    status_after_rollback = manager.status()

    assert activated["success"] is False
    assert activated["error_code"] == "BRIDGE_LIFECYCLE_RESULT_INVALID"
    assert status_after_activate["metadata"]["success"] is False
    assert status_after_activate["metadata"]["result"]["error_code"] == "BRIDGE_LIFECYCLE_RESULT_INVALID"
    assert rolled_back["success"] is False
    assert rolled_back["error_code"] == "BRIDGE_LIFECYCLE_FAILED"
    assert status_after_rollback["metadata"]["result"]["error_code"] == "BRIDGE_LIFECYCLE_FAILED"


def test_bridge_transport_request_contract_routes_to_client():
    class FakeClient:
        async def resolve_place(self, name):
            return {"success": True, "place": {"name": name}}

        async def get_robot_state(self):
            return {"success": True, "state": {"mode": "mock"}}

    async def run():
        transport = RosBridgeClientTransport(FakeClient())
        resolved = await transport.request("world.resolve_place", {"name": "厨房"})
        health = await transport.health_check()
        unsupported = await transport.request("unknown.capability", {})
        assert resolved["place"]["name"] == "厨房"
        assert health["success"] is True
        assert unsupported["error_code"] == "BRIDGE_CAPABILITY_UNSUPPORTED"

    asyncio.run(run())


def test_bridge_transport_health_rejects_malformed_success():
    class FakeClient:
        async def get_robot_state(self):
            return {"success": "false", "error_code": "", "reason": "string success"}

    async def run():
        transport = RosBridgeClientTransport(FakeClient())
        health = await transport.health_check()
        assert health["success"] is False
        assert health["error_code"] == "BRIDGE_HEALTH_RESULT_INVALID"
        assert health["state"]["success"] == "false"

    asyncio.run(run())


def test_bridge_transport_health_failure_without_error_code_gets_stable_code():
    class FakeClient:
        async def get_robot_state(self):
            return {"success": False, "reason": "not ready"}

    async def run():
        transport = RosBridgeClientTransport(FakeClient())
        health = await transport.health_check()
        assert health["success"] is False
        assert health["error_code"] == "BRIDGE_HEALTH_CHECK_FAILED"
        assert health["reason"] == "not ready"

    asyncio.run(run())


def test_runtime_does_not_import_rclpy():
    forbidden = ("import rclpy", "from rclpy")
    for root in [Path("agentic_runtime"), Path("agentic_os")]:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert not any(token in text for token in forbidden), path
