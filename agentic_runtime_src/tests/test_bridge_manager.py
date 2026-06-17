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
    installed = manager.install_profile(Ros2BridgeProfile(name="ros2_mock", source_workspace=str(source)), dry_run=True)
    status = manager.status()
    profile_path = tmp_path / "profiles" / "ros2_mock.yaml"
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert installed["status"] == "installed_profile"
    assert installed["dry_run"] is True
    assert installed["ros_distro"] == "humble"
    assert installed["bridge_endpoint"] == "ros2-cli://agentic-bridge"
    assert "ros2 node list" in installed["health_check_command"]
    assert status["installed"] is True
    assert status["metadata"]["profile"] == "ros2_mock"
    assert status["metadata"]["source_workspace"] == str(source)
    assert payload["status"] == "installed_profile"
    assert payload["installed_root"] == str(tmp_path / "bridges" / "ros2")


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


def test_runtime_does_not_import_rclpy():
    forbidden = ("import rclpy", "from rclpy")
    for root in [Path("agentic_runtime"), Path("agentic_os")]:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert not any(token in text for token in forbidden), path
