from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


TRUTH_STATUS_FIELDS = (
    "validate_config",
    "status",
    "health",
    "capabilities",
    "error_code",
    "missing",
    "details",
)


ROS_BRIDGE_IMPLEMENTED_MODES = ("cli",)
ROS_BRIDGE_UNSUPPORTED_MODES = ("service", "action", "topic", "http", "websocket")
LLM_IMPLEMENTED_BACKENDS = ("openai_compatible", "ollama_openai_compatible", "vllm_openai_compatible", "vllm", "litellm", "litellm_compatible")
LLM_RESERVED_BACKENDS = ("huggingface", "hf", "hflocal", "local")
LLM_UNSUPPORTED_BACKENDS: tuple[str, ...] = ()
HUMAN_IMPLEMENTED_MODES = ("file_queue",)
HUMAN_RESERVED_MODES = ("console", "http", "websocket")


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    kind: str
    validate_config: bool
    status: str
    health: str
    capabilities: tuple[str, ...] = ()
    error_code: str = ""
    missing: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
    implemented_modes: tuple[str, ...] = ()
    available_modes: tuple[str, ...] = ()
    unsupported_modes: tuple[str, ...] = ()
    reserved_modes: tuple[str, ...] = ()
    last_check: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        validate_mode_truth(
            available_modes=self.available_modes,
            implemented_modes=self.implemented_modes,
            unsupported_modes=self.unsupported_modes,
            reserved_modes=self.reserved_modes,
        )
        return {
            "name": self.name,
            "kind": self.kind,
            "validate_config": self.validate_config,
            "status": self.status,
            "health": self.health,
            "capabilities": list(self.capabilities),
            "error_code": self.error_code,
            "missing": list(self.missing),
            "details": dict(self.details),
            "implemented_modes": list(self.implemented_modes),
            "available_modes": list(self.available_modes),
            "unsupported_modes": list(self.unsupported_modes),
            "reserved_modes": list(self.reserved_modes),
            "last_check": self.last_check,
        }


def validate_mode_truth(
    *,
    available_modes: tuple[str, ...] | list[str],
    implemented_modes: tuple[str, ...] | list[str],
    unsupported_modes: tuple[str, ...] | list[str] = (),
    reserved_modes: tuple[str, ...] | list[str] = (),
) -> None:
    available = {str(item) for item in available_modes}
    implemented = {str(item) for item in implemented_modes}
    unsupported = {str(item) for item in unsupported_modes}
    reserved = {str(item) for item in reserved_modes}
    if not available.issubset(implemented):
        extra = ", ".join(sorted(available - implemented))
        raise ValueError(f"available_modes must be implemented: {extra}")
    overlap = available & (unsupported | reserved)
    if overlap:
        raise ValueError(f"available_modes overlap unsupported/reserved: {', '.join(sorted(overlap))}")


def ros_bridge_contract(mode: str = "cli") -> dict[str, Any]:
    mode = str(mode or "cli")
    cli_available = shutil.which("ros2") is not None
    if mode != "cli":
        return ProviderStatus(
            name="ros_bridge",
            kind="robot_bridge",
            validate_config=False,
            status="unsupported",
            health="unavailable",
            capabilities=(),
            error_code="ROS_BRIDGE_MODE_UNSUPPORTED",
            missing=(),
            details={"configured_mode": mode, "ros2_cli_available": cli_available},
            implemented_modes=ROS_BRIDGE_IMPLEMENTED_MODES,
            available_modes=(),
            unsupported_modes=ROS_BRIDGE_UNSUPPORTED_MODES,
        ).to_dict()
    missing = () if cli_available else ("ros2_cli",)
    return ProviderStatus(
        name="ros_bridge",
        kind="robot_bridge",
        validate_config=cli_available,
        status="ready" if cli_available else "unavailable",
        health="healthy" if cli_available else "dependency_missing",
        capabilities=("resolve_place", "robot_state", "navigate_to", "inspect_area", "stop", "report", "human_bridge"),
        error_code="" if cli_available else "ROS2_CLI_MISSING",
        missing=missing,
        details={"configured_mode": mode, "provider": "ros2_cli", "ros2_cli_available": cli_available},
        implemented_modes=ROS_BRIDGE_IMPLEMENTED_MODES,
        available_modes=("cli",) if cli_available else (),
        unsupported_modes=ROS_BRIDGE_UNSUPPORTED_MODES,
    ).to_dict()


def llm_provider_contracts(status: dict[str, Any]) -> dict[str, Any]:
    providers = [dict(item) for item in status.get("providers", []) if isinstance(item, dict)]
    provider_contracts: list[dict[str, Any]] = []
    available_modes: set[str] = set()
    missing: set[str] = set()
    error_code = ""
    for provider in providers:
        backend = str(provider.get("backend") or "")
        state = str(provider.get("state") or "unavailable")
        reason = str(provider.get("reason") or "")
        provider_missing = _missing_from_reason(reason)
        if state != "configured":
            missing.update(f"{backend}:{item}" for item in provider_missing)
        if provider.get("error_code") and not error_code:
            error_code = str(provider["error_code"])
        if state == "configured" and backend in LLM_IMPLEMENTED_BACKENDS:
            available_modes.add(backend)
        provider_contracts.append(
            ProviderStatus(
                name=str(provider.get("name") or backend or "unconfigured"),
                kind="llm",
                validate_config=state == "configured",
                status="ready" if state == "configured" else "unavailable",
                health="healthy" if state == "configured" else _llm_health(provider),
                capabilities=tuple(str(item) for item in provider.get("capabilities", []) or ()),
                error_code=str(provider.get("error_code") or ""),
                missing=tuple(provider_missing),
                details={key: provider[key] for key in sorted(provider) if key not in {"capabilities"}},
                implemented_modes=LLM_IMPLEMENTED_BACKENDS,
                available_modes=(backend,) if state == "configured" and backend in LLM_IMPLEMENTED_BACKENDS else (),
                unsupported_modes=LLM_UNSUPPORTED_BACKENDS,
                reserved_modes=LLM_RESERVED_BACKENDS,
            ).to_dict()
        )
    aggregate_status = ProviderStatus(
        name="llm",
        kind="llm",
        validate_config=bool(available_modes),
        status="ready" if available_modes else "unavailable",
        health="healthy" if available_modes else "unconfigured",
        capabilities=tuple(sorted({cap for provider in providers for cap in provider.get("capabilities", []) or ()})),
        error_code="" if available_modes else (error_code or "LLM_PROVIDER_UNCONFIGURED"),
        missing=tuple(sorted(missing)),
        details={"providers": provider_contracts},
        implemented_modes=LLM_IMPLEMENTED_BACKENDS,
        available_modes=tuple(sorted(available_modes)),
        unsupported_modes=LLM_UNSUPPORTED_BACKENDS,
        reserved_modes=LLM_RESERVED_BACKENDS,
    ).to_dict()
    return aggregate_status


def human_operator_contract(status: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(status or {})
    channel = data.get("human_channel") if isinstance(data.get("human_channel"), dict) else data
    channel = dict(channel or {})
    file_queue_ready = channel.get("success") is True and str(channel.get("backend") or "") in {
        "file_human_queue",
        "runtime_human_skill",
        "",
    }
    missing = () if file_queue_ready else ("file_queue",)
    return ProviderStatus(
        name="human_operator",
        kind="human",
        validate_config=file_queue_ready,
        status="ready" if file_queue_ready else "unavailable",
        health="healthy" if file_queue_ready else "unconfigured",
        capabilities=("ask", "answer", "cancel", "timeout", "status", "audit"),
        error_code="" if file_queue_ready else str(channel.get("error_code") or data.get("error_code") or "HUMAN_BACKEND_UNAVAILABLE"),
        missing=missing,
        details={"status": data},
        implemented_modes=HUMAN_IMPLEMENTED_MODES,
        available_modes=("file_queue",) if file_queue_ready else (),
        reserved_modes=HUMAN_RESERVED_MODES,
    ).to_dict()


def manager_provider_contract(
    *,
    name: str,
    kind: str,
    status: dict[str, Any],
    capabilities: tuple[str, ...],
    implemented_modes: tuple[str, ...] = (),
    available_modes: tuple[str, ...] = (),
    unsupported_modes: tuple[str, ...] = (),
    reserved_modes: tuple[str, ...] = (),
) -> dict[str, Any]:
    data = dict(status or {})
    error_code = _status_error_code(data)
    state = str(data.get("state") or ("unavailable" if data.get("success") is False else "ready"))
    ready = state == "ready" and not error_code and data.get("success", True) is not False
    modes = available_modes or implemented_modes
    return ProviderStatus(
        name=name,
        kind=kind,
        validate_config=ready,
        status="ready" if ready else state,
        health="healthy" if ready else _manager_health(data, error_code),
        capabilities=capabilities,
        error_code=error_code,
        missing=tuple(str(item) for item in data.get("missing", []) or ()),
        details=data,
        implemented_modes=implemented_modes,
        available_modes=modes if ready else (),
        unsupported_modes=unsupported_modes,
        reserved_modes=reserved_modes,
    ).to_dict()


def _missing_from_reason(reason: str) -> tuple[str, ...]:
    if "missing required config:" not in reason:
        if "missing dependency:" in reason:
            return (reason.split("missing dependency:", 1)[1].strip(),)
        return ()
    missing_text = reason.split("missing required config:", 1)[1]
    return tuple(item.strip() for item in missing_text.split(",") if item.strip())


def _llm_health(provider: dict[str, Any]) -> str:
    error_code = str(provider.get("error_code") or "")
    if error_code.endswith("DEPENDENCY_MISSING"):
        return "dependency_missing"
    if error_code.endswith("UNCONFIGURED"):
        return "unconfigured"
    if error_code:
        return "unavailable"
    return "disabled" if provider.get("enabled") is False else "unavailable"


def _status_error_code(status: dict[str, Any]) -> str:
    if status.get("error_code"):
        return str(status["error_code"])
    last_error = status.get("last_error")
    if isinstance(last_error, dict) and last_error.get("error_code"):
        return str(last_error["error_code"])
    index = status.get("index")
    if isinstance(index, dict) and index.get("error_code"):
        return str(index["error_code"])
    return ""


def _manager_health(status: dict[str, Any], error_code: str) -> str:
    if error_code:
        if "UNCONFIGURED" in error_code:
            return "unconfigured"
        if "DEPENDENCY" in error_code or "MISSING" in error_code:
            return "dependency_missing"
        return "unavailable"
    state = str(status.get("state") or "").lower()
    if state in {"ready", "running"}:
        return "healthy"
    if state:
        return state
    return "unavailable"
