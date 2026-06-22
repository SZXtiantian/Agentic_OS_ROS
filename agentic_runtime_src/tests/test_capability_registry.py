import yaml

from agentic_os.kernel.capability import CapabilityKind, CapabilityRegistry, CapabilitySpec
from agentic_runtime.hardware_adapter import Ros2BridgeProfile
from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def test_kernel_capability_registry_loads_task_level_capabilities(runtime_src):
    registry = CapabilityRegistry().load_skill_manifests(runtime_src / "skills")

    navigate = registry.get("robot.navigate_to")
    inspect = registry.get("robot.inspect_area")
    remember = registry.get("memory.remember")
    state = registry.get("robot.get_state")

    assert navigate is not None
    assert navigate.kind == CapabilityKind.NAV2_ACTION
    assert navigate.ros2 is not None
    assert navigate.ros2.name == "/agentic/robot/navigate_to_place"
    assert navigate.ros2.backend_name == "/navigate_to_pose"
    assert "base" in navigate.resource_locks

    assert inspect is not None
    assert inspect.kind == CapabilityKind.PERCEPTION
    assert inspect.ros2 is not None
    assert inspect.ros2.name == "/agentic/perception/inspect_area"

    assert state is not None
    assert state.kind == CapabilityKind.ROS2_SERVICE
    assert state.ros2 is not None
    assert state.ros2.name == "/agentic/robot/get_state"

    assert remember is not None
    assert remember.kind == CapabilityKind.RUNTIME_INTERNAL
    assert registry.validate() == []


def test_kernel_capability_contract_rejects_unsafe_robot_capability():
    spec = CapabilitySpec(name="robot.navigate_to", kind=CapabilityKind.ROS2_ACTION)

    failures = spec.validate_os_contract()

    assert any("permission" in item for item in failures)
    assert any("resource locks" in item for item in failures)
    assert any("interface name" in item for item in failures)


def test_kernel_capability_registry_rejects_simulated_backend_manifest():
    registry = CapabilityRegistry()

    try:
        registry.register_skill_manifest({"name": "robot.fake_success", "backend": {"type": "mock"}})
    except ValueError as exc:
        assert "simulated capability backend is disabled" in str(exc)
    else:
        raise AssertionError("simulated capability backend manifest must be rejected")


def test_runtime_skill_registry_exposes_kernel_capabilities():
    server = create_test_runtime_server()

    names = [spec.name for spec in server.registry.capabilities.list()]

    assert "robot.navigate_to" in names
    assert server.registry.capabilities.get("robot.navigate_to").kind == CapabilityKind.NAV2_ACTION


def test_bridge_profile_persists_capability_specs(tmp_path):
    server = create_test_runtime_server()
    server.bridge_manager.bridge_root = tmp_path / "bridges" / "ros2"
    server.bridge_manager.profile_root = tmp_path / "profiles"
    server.bridge_manager.bridge_root.mkdir(parents=True, exist_ok=True)
    server.bridge_manager.profile_root.mkdir(parents=True, exist_ok=True)

    result = server.bridge_manager.install_profile(Ros2BridgeProfile(name="ros2_default"))
    profile_path = server.bridge_manager.profile_root / "ros2_default.yaml"
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8"))

    assert result["status"] == "installed_profile"
    assert profile_path.exists()
    assert "robot.navigate_to" in payload["capabilities"]
    assert any(item["name"] == "robot.navigate_to" and item["kind"] == CapabilityKind.NAV2_ACTION for item in payload["capability_specs"])
