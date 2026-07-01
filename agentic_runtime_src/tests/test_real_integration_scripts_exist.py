from __future__ import annotations

import os
import subprocess
from pathlib import Path


REAL_SCRIPTS = [
    "verify_real_ros2.sh",
    "verify_real_llm.sh",
    "verify_real_human.sh",
    "verify_real_scheduler_llm.sh",
    "verify_real_scheduler_capability.sh",
]
ROOT_SCHEDULER_VERIFICATION_SCRIPTS = [
    "verify_real_scheduler_llm.sh",
    "verify_real_scheduler_capability.sh",
    "verify_no_fake_mock.sh",
]


def test_foundation_verification_scripts_exist_and_are_executable(runtime_src: Path):
    for name in [
        "verify_foundation.sh",
        "verify_capability_truth.sh",
        "verify_no_mvp_language.sh",
        "verify_no_fake_mock.sh",
        *REAL_SCRIPTS,
    ]:
        path = runtime_src / "scripts" / name
        assert path.exists(), name
        assert os.access(path, os.X_OK), name


def test_root_scheduler_verification_script_wrappers_exist_and_delegate_to_runtime_scripts(repo_root: Path):
    for name in ROOT_SCHEDULER_VERIFICATION_SCRIPTS:
        path = repo_root / "scripts" / name

        assert path.exists(), name
        assert os.access(path, os.X_OK), name
        text = path.read_text(encoding="utf-8")
        assert 'cd "$(dirname "$0")/.."' in text
        assert f"exec agentic_runtime_src/scripts/{name}" in text


def test_real_dependency_scripts_report_unverified_without_env(runtime_src: Path):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("AGENTIC_VERIFY_REAL_") or key.startswith("AGENTIC_REAL_LLM_"):
            env.pop(key)

    for name in REAL_SCRIPTS:
        result = subprocess.run(
            [str(runtime_src / "scripts" / name)],
            cwd=runtime_src,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 2, result.stderr
        assert "UNVERIFIED_REAL_DEPENDENCY" in result.stdout


def test_real_scheduler_capability_script_enabled_reports_structured_result(runtime_src: Path):
    env = os.environ.copy()
    env["AGENTIC_VERIFY_REAL_SCHEDULER_CAPABILITY"] = "1"
    env["AGENTIC_RUNTIME_CONFIG"] = str(runtime_src / "configs" / "runtime.yaml")
    env["AGENTIC_VAR"] = str(runtime_src / "var" / "test_real_scheduler_capability")

    result = subprocess.run(
        [str(runtime_src / "scripts" / "verify_real_scheduler_capability.sh")],
        cwd=runtime_src,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode in {0, 1, 2}
    assert "CHECK_NAME=real_scheduler_capability" in result.stdout
    assert "RESULT=" in result.stdout
    assert "ERROR_CODE=" in result.stdout
    assert "NEXT_ACTION=" in result.stdout
    assert "Traceback" not in result.stderr


def test_real_scheduler_capability_script_requires_dispatch_syscall_and_audit_trace(runtime_src: Path):
    script = (runtime_src / "scripts" / "verify_real_scheduler_capability.sh").read_text(encoding="utf-8")

    assert "source_if_exists" in script
    assert "AGENTIC_ROS2_SETUP" in script
    assert "AGENTIC_ROS2_BRIDGE_SETUP" in script
    assert "AGENTIC_VERIFY_BRIDGE_PROFILE_FILE" in script
    assert "AGENTIC_VERIFY_START_READONLY_STATE_BRIDGE" in script
    assert "start_readonly_state_bridge_if_requested" in script
    assert "AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_STATUS" in script
    assert "AGENTIC_VERIFY_AUTO_STARTED_STATE_BRIDGE_LOG" in script
    assert "cleanup_readonly_state_bridge" in script
    assert "_ros_graph_snapshot" in script
    assert "_bridge_profile_dependency_hint" in script
    assert "_load_bridge_profile" in script
    assert "_ROS_GRAPH_QUERY_ERRORS" in script
    assert "_ros_discovery_attempts" in script
    assert "AGENTIC_VERIFY_ROS_DISCOVERY_ATTEMPTS" in script
    assert "AGENTIC_VERIFY_ROS_DISCOVERY_RETRY_DELAY_S" in script
    assert "discovery_attempts={discovery_attempts}" in script
    assert '["ros2", "node", "list"]' in script
    assert '["ros2", "topic", "list"]' in script
    assert "preflight_ros_interface" in script
    assert "_missing_ros_interface_next_action" in script
    assert "_ros_interface_start_hint" in script
    assert "_ros_interface_executable_hints" in script
    assert "_ros_package_executable_status" in script
    assert "_readonly_state_bridge_auto_start_hint" in script
    assert "required={required_name}" in script
    assert "visible_{plural}" in script
    assert "command={' '.join(command)}" in script
    assert "start_command={start_hint}" in script
    assert "bridge_executable={package}/{executable}:{status}" in script
    assert "executable_command=ros2 pkg executables {package}" in script
    assert '["ros2", "pkg", "executables", package]' in script
    assert "ros2 run agentic_capability_bridge state_bridge_node" in script
    assert '["ros2", "service", "list"]' in script
    assert '["ros2", "action", "list"]' in script
    assert "ROS_SERVICE_UNAVAILABLE" in script
    assert "ROS_ACTION_UNAVAILABLE" in script
    assert "scheduler.node.dispatched" in script
    assert "dispatched_syscall_id" in script
    assert "resource_lease_id" in script
    assert "recent_syscalls" in script
    assert "recent_audit_records" in script
    assert "from agentic_runtime.verification.scheduler_capability import backend_next_steps, backend_step_hints, dependency_next_action, live_ros_graph_evidence, profile_dependency_evidence, sanitize_reason, summarize_cli_stderr" in script
    assert "profile_dependency_evidence" in script
    assert "backend_next_steps" in script
    assert "backend_step_hints" in script
    assert '-p "bridge_profile_file:=$AGENTIC_VERIFY_BRIDGE_PROFILE_FILE"' in script
    assert "dependency_next_action" in script
    assert "summarize_cli_stderr(result.stderr)" in script
    assert "ensure KernelService recent syscalls include the dispatched scheduler capability syscall" in script


def test_real_scheduler_llm_script_uses_real_context_fact_producer_not_direct_fact_insertion(runtime_src: Path):
    script = (runtime_src / "scripts" / "verify_real_scheduler_llm.sh").read_text(encoding="utf-8")

    assert "load_llm_config().require_ready()" in script
    assert "AGENTIC_REAL_LLM_BASE_URL" in script
    assert "AGENTIC_REAL_LLM_API_KEY" in script
    assert "AGENTIC_REAL_LLM_MODEL" in script
    assert "EnvironmentFact.create" not in script
    assert "source_syscall_id=\"ksc_real_scheduler_verify_context\"" not in script
    assert "source_audit_id=\"audit_real_scheduler_verify_context\"" not in script
    assert "SchedulerLLMVerificationInterventionProvider" in script
    assert "AGENTIC_VERIFY_REAL_SCHEDULER_LLM" in script
    assert 'request.resource.resource_type == "llm"' in script
    assert 'request.resource.resource_id == "external_provider"' in script
    assert "ContextQuery" in script
    assert "operation_type=\"ctx_get\"" in script
    assert "verified_fact.source_is_verified()" in script
    assert "ensure scheduler LLM verification fact is produced by a real KernelService-dispatched TaskNode" in script


def test_no_fake_mock_script_scans_production_skill_manifest_roots(runtime_src: Path):
    script = (runtime_src / "scripts" / "verify_no_fake_mock.sh").read_text(encoding="utf-8")

    assert 'ROOT / "system_skills"' in script


def test_real_llm_script_can_resolve_configured_models_yaml_provider(runtime_src: Path):
    script = (runtime_src / "scripts" / "verify_real_llm.sh").read_text(encoding="utf-8")

    assert "load_llm_config().require_ready()" in script
    assert "AGENTIC_REAL_LLM_BASE_URL" in script
    assert "AGENTIC_REAL_LLM_API_KEY" in script
    assert "AGENTIC_REAL_LLM_MODEL" in script
    assert "api_key_present=" in script
