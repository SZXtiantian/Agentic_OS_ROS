from __future__ import annotations

from dataclasses import replace

from agentic_runtime.config import RuntimeConfig
from agentic_runtime.provider_contracts import ROS_BRIDGE_UNSUPPORTED_MODES, ros_bridge_contract, validate_mode_truth
from agentic_runtime.ros_bridge_client.client import RosBridgeModeUnsupportedError, create_ros_bridge_client


def test_ros_bridge_only_cli_can_be_available():
    contract = ros_bridge_contract("cli")

    validate_mode_truth(
        available_modes=contract["available_modes"],
        implemented_modes=contract["implemented_modes"],
        unsupported_modes=contract["unsupported_modes"],
        reserved_modes=contract["reserved_modes"],
    )
    assert contract["implemented_modes"] == ["cli"]
    assert set(ROS_BRIDGE_UNSUPPORTED_MODES).issubset(set(contract["unsupported_modes"]))
    assert not (set(contract["available_modes"]) & set(contract["unsupported_modes"]))


def test_unimplemented_ros_bridge_modes_return_stable_unsupported_error(tmp_path):
    for mode in ROS_BRIDGE_UNSUPPORTED_MODES:
        config = replace(RuntimeConfig.load(), ros_bridge_mode=mode, repo_root=tmp_path)
        try:
            create_ros_bridge_client(config)
        except RosBridgeModeUnsupportedError as exc:
            assert exc.error_code == "ROS_BRIDGE_MODE_UNSUPPORTED"
            assert exc.status["error_code"] == "ROS_BRIDGE_MODE_UNSUPPORTED"
            assert exc.status["available_modes"] == []
            assert mode in exc.status["unsupported_modes"]
        else:
            raise AssertionError(f"{mode} must not create a bridge client")
