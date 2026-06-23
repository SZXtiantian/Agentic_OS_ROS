from __future__ import annotations

import importlib.util
import os
import threading
from typing import Any

from agentic_os.kernel.access import AccessManager, AccessRequest, AccessResource, AccessSubject
from agentic_os.kernel.context import GenerationSnapshot
from agentic_os.kernel.hooks import KernelEventSink
from agentic_os.kernel.system_call import KernelResponse, KernelSyscall, LLMQuery

from .errors import LLMCoreErrorCode
from .local import LocalBackendProvider
from .provider import (
    HuggingFaceProvider,
    LiteLLMProvider,
    LLMProvider,
    OpenAICompatibleProvider,
    UnsupportedLLMProvider,
    VLLMOpenAIProvider,
)
from .routing import SequentialRouting, SmartRouting
from .schema import LLMConfig
from .utils import enforce_json_response, normalize_llm_configs


class LLMAdapter:
    def __init__(
        self,
        llm_configs: list[LLMConfig | dict],
        routing_strategy: str = "sequential",
        providers: dict[str, LLMProvider] | None = None,
        access_manager: AccessManager | None = None,
        event_sink: KernelEventSink | None = None,
    ) -> None:
        self.llm_configs = normalize_llm_configs(llm_configs)
        self.providers = dict(providers or {})
        self.access_manager = access_manager
        self.event_sink = event_sink
        self._active: dict[str, threading.Event] = {}
        self._active_lock = threading.Lock()
        if routing_strategy == "smart":
            self.router = SmartRouting(self.llm_configs)
        else:
            self.router = SequentialRouting(self.llm_configs)

    def address_request(self, syscall: KernelSyscall) -> KernelResponse:
        if syscall.operation_type in {"llm_status", "status"}:
            return self._status_response(_cancel_call_id(syscall.params))
        if syscall.operation_type in {"llm_cancel", "cancel"}:
            return self.cancel(_cancel_call_id(syscall.params))
        query = getattr(syscall, "query", None)
        if not isinstance(query, LLMQuery):
            query = LLMQuery(
                operation_type=syscall.operation_type,
                params=dict(syscall.params),
                messages=list(syscall.params.get("messages") or []),
                tools=syscall.params.get("tools"),
                selected_llms=syscall.params.get("selected_llms"),
                response_format=syscall.params.get("response_format"),
                action_type=str(syscall.params.get("action_type") or _action_type_from_operation(syscall.operation_type)),
            )
        access_response = self._check_external_access(syscall, query)
        if access_response is not None:
            self._audit_provider_result(query, None, access_response, access_gate=True)
            return access_response
        cancel_event = self._register_active(syscall.syscall_id)
        try:
            response = self.complete(query)
            if cancel_event.is_set():
                return KernelResponse.error(LLMCoreErrorCode.CANCELLED, metadata={"call_id": syscall.syscall_id})
            response.metadata.setdefault("call_id", syscall.syscall_id)
            return response
        finally:
            self._unregister_active(syscall.syscall_id)

    def address_batch(self, syscalls: list[KernelSyscall]) -> list[KernelResponse]:
        responses: list[KernelResponse | None] = [None] * len(syscalls)
        indexed_queries: list[tuple[int, KernelSyscall, LLMQuery, threading.Event]] = []
        for index, syscall in enumerate(syscalls):
            if syscall.operation_type in {"llm_status", "status"}:
                responses[index] = self._status_response(_cancel_call_id(syscall.params))
                continue
            if syscall.operation_type in {"llm_cancel", "cancel"}:
                responses[index] = self.cancel(_cancel_call_id(syscall.params))
                continue
            query = getattr(syscall, "query", None)
            if not isinstance(query, LLMQuery):
                query = LLMQuery(
                    operation_type=syscall.operation_type,
                    params=dict(syscall.params),
                    messages=list(syscall.params.get("messages") or []),
                    tools=syscall.params.get("tools"),
                    selected_llms=syscall.params.get("selected_llms"),
                    response_format=syscall.params.get("response_format"),
                    action_type=str(syscall.params.get("action_type", "chat")),
                )
            access_response = self._check_external_access(syscall, query)
            if access_response is not None:
                self._audit_provider_result(query, None, access_response, batch=True, access_gate=True)
                responses[index] = access_response
                continue
            cancel_event = self._register_active(syscall.syscall_id)
            indexed_queries.append((index, syscall, query, cancel_event))
        if indexed_queries:
            try:
                batch_responses = self.complete_batch([item[2] for item in indexed_queries])
                for (index, syscall, _query, cancel_event), response in zip(indexed_queries, batch_responses, strict=False):
                    if cancel_event.is_set():
                        responses[index] = KernelResponse.error(LLMCoreErrorCode.CANCELLED, metadata={"call_id": syscall.syscall_id})
                    else:
                        response.metadata.setdefault("call_id", syscall.syscall_id)
                        responses[index] = response
                for index, syscall, _query, _cancel_event in indexed_queries[len(batch_responses) :]:
                    responses[index] = KernelResponse.error(
                        LLMCoreErrorCode.RESPONSE_INVALID,
                        metadata={"reason": "missing batch response", "call_id": syscall.syscall_id},
                    )
            finally:
                for _index, syscall, _query, _cancel_event in indexed_queries:
                    self._unregister_active(syscall.syscall_id)
        return [response or KernelResponse.error(LLMCoreErrorCode.RESPONSE_INVALID) for response in responses]

    def complete(self, query: LLMQuery) -> KernelResponse:
        if query.operation_type in {"llm_status", "status"}:
            return self._status_response(_cancel_call_id(query.params))
        if query.operation_type in {"llm_cancel", "cancel"}:
            return self.cancel(str(query.params.get("call_id") or query.params.get("syscall_id") or ""))
        candidates = self.router.candidates(selected_llms=query.selected_llms, capability=query.action_type)
        if not candidates:
            response = KernelResponse.error(
                LLMCoreErrorCode.PROVIDER_UNAVAILABLE,
                metadata={"reason": "no enabled LLM provider configured"},
            )
            self._audit_provider_result(query, None, response)
            return response

        last_response: KernelResponse | None = None
        for config in candidates:
            provider = self._provider_for(config)
            response = enforce_json_response(query.response_format, self._complete_with_provider(provider, query))
            self._audit_provider_result(query, config, response)
            if response.success is True:
                response.metadata.setdefault("model", config.name)
                return response
            last_response = response
        final = last_response or KernelResponse(False, error_code=LLMCoreErrorCode.MODEL_NOT_FOUND)
        final.metadata.setdefault("candidates", [config.name for config in candidates])
        return final

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        if not queries:
            return []
        candidates = self.router.candidates(selected_llms=queries[0].selected_llms, capability=queries[0].action_type)
        if not candidates:
            responses = [
                KernelResponse.error(
                    LLMCoreErrorCode.PROVIDER_UNAVAILABLE,
                    metadata={"reason": "no enabled LLM provider configured"},
                )
                for _ in queries
            ]
            for query, response in zip(queries, responses, strict=False):
                self._audit_provider_result(query, None, response, batch=True)
            return responses

        last_responses: list[KernelResponse] | None = None
        for config in candidates:
            provider = self._provider_for(config)
            if hasattr(provider, "complete_batch"):
                responses = self._complete_batch_with_provider(provider, queries)
            else:
                responses = [self._complete_with_provider(provider, query) for query in queries]
            for response in responses:
                response.metadata.setdefault("model", config.name)
            for query, response in zip(queries, responses, strict=False):
                self._audit_provider_result(query, config, response, batch=True)
            if any(response.success is True for response in responses):
                return _normalize_batch_length(responses, len(queries))
            last_responses = responses
        return _normalize_batch_length(
            last_responses or [KernelResponse.error(LLMCoreErrorCode.MODEL_NOT_FOUND) for _ in queries],
            len(queries),
        )

    def complete_with_time_slice(
        self,
        query: LLMQuery,
        time_slice_s: float,
        snapshot: GenerationSnapshot | None = None,
    ) -> tuple[KernelResponse, GenerationSnapshot | None]:
        access_response = self._check_external_access(None, query)
        if access_response is not None:
            self._audit_provider_result(query, None, access_response, time_slice=True, access_gate=True)
            return access_response, None
        candidates = self.router.candidates(selected_llms=query.selected_llms, capability=query.action_type)
        if not candidates:
            response = KernelResponse.error(LLMCoreErrorCode.MODEL_NOT_FOUND)
            self._audit_provider_result(query, None, response, time_slice=True)
            return response, None
        config = candidates[0]
        provider = self._provider_for(config)
        if hasattr(provider, "complete_with_time_slice"):
            response, next_snapshot = provider.complete_with_time_slice(query, time_slice_s, snapshot)
            response = self._normalize_provider_response(response, operation="complete_with_time_slice")
            response.metadata.setdefault("model", config.name)
            self._audit_provider_result(query, config, response, time_slice=True)
            return response, next_snapshot
        response = self.complete(query)
        response.metadata["non_preemptible_llm_call"] = True
        return response, None

    def _provider_for(self, config: LLMConfig) -> LLMProvider:
        if config.backend in {"mock", "fake", "stub", "dummy"}:
            return UnsupportedLLMProvider(config)
        if config.name in self.providers:
            return self.providers[config.name]
        if config.backend in self.providers:
            return self.providers[config.backend]
        if config.backend in {"litellm", "litellm_compatible"}:
            return LiteLLMProvider(config)
        if config.backend in {"openai_compatible", "ollama_openai_compatible", "vllm_openai_compatible"}:
            return OpenAICompatibleProvider(config)
        if config.backend in {"vllm"}:
            return VLLMOpenAIProvider(config)
        if config.backend in {"huggingface", "hf", "hflocal"}:
            return HuggingFaceProvider(config)
        if config.backend in {"local"}:
            return LocalBackendProvider(config)
        return UnsupportedLLMProvider(config)

    def _complete_with_provider(self, provider: LLMProvider, query: LLMQuery) -> KernelResponse:
        try:
            result = provider.complete(query)
        except Exception as exc:
            return KernelResponse.error(LLMCoreErrorCode.PROVIDER_ERROR, metadata={"reason": str(exc)})
        return self._normalize_provider_response(result, operation="complete")

    def _complete_batch_with_provider(self, provider: LLMProvider, queries: list[LLMQuery]) -> list[KernelResponse]:
        try:
            result = provider.complete_batch(queries)
        except Exception as exc:
            return [
                KernelResponse.error(
                    LLMCoreErrorCode.PROVIDER_ERROR,
                    metadata={"reason": str(exc), "batch": True},
                )
                for _query in queries
            ]
        if not isinstance(result, (list, tuple)):
            return [
                KernelResponse.error(
                    LLMCoreErrorCode.PROVIDER_RESULT_INVALID,
                    metadata={"reason": f"provider complete_batch returned {type(result).__name__}"},
                )
            ]
        return [self._normalize_provider_response(item, operation="complete_batch") for item in result]

    def _normalize_provider_response(self, result: Any, *, operation: str) -> KernelResponse:
        if isinstance(result, KernelResponse):
            if not isinstance(result.success, bool):
                return KernelResponse.error(
                    LLMCoreErrorCode.PROVIDER_RESULT_INVALID,
                    metadata={
                        "reason": f"provider {operation} response success field must be boolean",
                        "success_type": type(result.success).__name__,
                    },
                )
            if result.success is False and not result.error_code:
                return KernelResponse.error(
                    LLMCoreErrorCode.PROVIDER_ERROR,
                    metadata={
                        "reason": f"provider {operation} failed without error_code",
                        "provider_metadata": dict(result.metadata),
                    },
                )
            return result
        return KernelResponse.error(
            LLMCoreErrorCode.PROVIDER_RESULT_INVALID,
            metadata={"reason": f"provider {operation} returned {type(result).__name__}"},
        )

    def status(self, call_id: str = "") -> dict[str, Any]:
        providers = []
        for config in self.llm_configs:
            provider_status = self._config_status(config)
            providers.append(
                {
                    "name": config.name,
                    "backend": config.backend,
                    "enabled": config.enabled,
                    "state": provider_status["state"],
                    "error_code": provider_status["error_code"],
                    "reason": provider_status["reason"],
                    "capabilities": list(config.capabilities),
                }
            )
        with self._active_lock:
            active = sorted(self._active)
        if call_id:
            if call_id not in active:
                result = {
                    "success": False,
                    "error_code": "SYSCALL_NOT_FOUND",
                    "reason": "LLM call_id is not active",
                    "call_id": call_id,
                    "active": active,
                    "active_count": len(active),
                }
                self._audit_status_result(call_id, result)
                return result
            result = {
                "success": True,
                "call_id": call_id,
                "active_call": {"call_id": call_id},
                "active": active,
                "active_count": len(active),
            }
            self._audit_status_result(call_id, result)
            return result
        return {
            "providers": providers,
            "state": "ready" if any(item["state"] == "configured" for item in providers) else "unavailable",
            "active": active,
            "active_count": len(active),
        }

    def _status_response(self, call_id: str = "") -> KernelResponse:
        status = self.status(call_id=call_id)
        if call_id:
            if status.get("success") is True:
                return KernelResponse.ok(status, data=status)
            return KernelResponse.error(str(status.get("error_code") or "SYSCALL_NOT_FOUND"), metadata=status)
        return KernelResponse.ok({"status": status}, data={"status": status})

    def cancel(self, call_id: str = "") -> KernelResponse:
        if not call_id:
            response = KernelResponse.error("SYSCALL_NOT_FOUND", metadata={"reason": "call_id required"})
            self._audit_cancel_result(call_id, response)
            return response
        with self._active_lock:
            event = self._active.get(call_id)
        if event is None:
            response = KernelResponse.error("SYSCALL_NOT_FOUND", metadata={"call_id": call_id})
            self._audit_cancel_result(call_id, response)
            return response
        event.set()
        response = KernelResponse.ok({"cancelled": [call_id]}, metadata={"call_id": call_id, "status": "cancel_requested"})
        self._audit_cancel_result(call_id, response)
        return response

    def _register_active(self, call_id: str) -> threading.Event:
        event = threading.Event()
        with self._active_lock:
            self._active[call_id] = event
        return event

    def _unregister_active(self, call_id: str) -> None:
        with self._active_lock:
            self._active.pop(call_id, None)

    def _config_status(self, config: LLMConfig) -> dict[str, str]:
        if not config.enabled:
            return {"state": "disabled", "error_code": "", "reason": ""}
        if config.backend in {"mock", "fake", "stub", "dummy"}:
            return {
                "state": "unavailable",
                "error_code": LLMCoreErrorCode.PROVIDER_UNAVAILABLE,
                "reason": "mock/fake/stub/dummy LLM backends are disabled",
            }
        if config.backend in {"openai_compatible", "ollama_openai_compatible", "vllm_openai_compatible", "vllm"}:
            missing = []
            if not config.hostname:
                missing.append("base_url")
            if not (config.api_key or (config.api_key_env and os.environ.get(config.api_key_env))):
                missing.append("api_key")
            if not str(config.model or "").strip():
                missing.append("model")
            if missing:
                return {
                    "state": "unavailable",
                    "error_code": LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                    "reason": f"missing required config: {', '.join(missing)}",
                }
            return {"state": "configured", "error_code": "", "reason": ""}
        if config.backend in {"litellm", "litellm_compatible"}:
            if not str(config.model or "").strip():
                return {
                    "state": "unavailable",
                    "error_code": LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                    "reason": "missing required config: model",
                }
            if importlib.util.find_spec("litellm") is None:
                return {
                    "state": "unavailable",
                    "error_code": LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING,
                    "reason": "missing dependency: litellm",
                }
            return {"state": "configured", "error_code": "", "reason": ""}
        if config.backend in {"huggingface", "hf", "hflocal"}:
            if not str(config.model or "").strip():
                return {
                    "state": "unavailable",
                    "error_code": LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                    "reason": "missing required config: model",
                }
            if importlib.util.find_spec("transformers") is None:
                return {
                    "state": "unavailable",
                    "error_code": LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING,
                    "reason": "missing dependency: transformers",
                }
            return {
                "state": "unavailable",
                "error_code": LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                "reason": "local HuggingFace generation pipeline is not configured",
            }
        if config.backend == "local":
            if not str(config.model or "").strip():
                return {
                    "state": "unavailable",
                    "error_code": LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                    "reason": "missing required config: model",
                }
            return {
                "state": "unavailable",
                "error_code": LLMCoreErrorCode.PROVIDER_UNCONFIGURED,
                "reason": "local LLM backend is not configured",
            }
        return {
            "state": "unavailable",
            "error_code": LLMCoreErrorCode.PROVIDER_UNAVAILABLE,
            "reason": f"unsupported backend: {config.backend}",
        }

    def _check_external_access(self, syscall: KernelSyscall | None, query: LLMQuery) -> KernelResponse | None:
        candidates = self.router.candidates(selected_llms=query.selected_llms, capability=query.action_type)
        if not any(self._config_status(config).get("state") == "configured" for config in candidates):
            return None
        if self.access_manager is None:
            return KernelResponse.error(
                "ACCESS_MANAGER_UNAVAILABLE",
                metadata={
                    "reason": "external LLM provider calls require a kernel access manager",
                    "requires_intervention": False,
                },
            )
        syscall_params = syscall.params if syscall is not None else {}
        permissions = tuple(query.metadata.get("permissions") or syscall_params.get("permissions") or ())
        if "llm.external.call" not in permissions:
            return KernelResponse.error(
                "ACCESS_DENIED",
                metadata={
                    "reason": "external LLM provider calls require explicit llm.external.call permission",
                    "requires_intervention": False,
                },
            )
        agent_name = str(
            (syscall.agent_name if syscall is not None else "")
            or query.metadata.get("agent_name")
            or query.metadata.get("app_id")
            or "llm_kernel"
        )
        decision = self.access_manager.check(
            AccessRequest(
                subject=AccessSubject(
                    agent_name=agent_name,
                    app_id=str(query.metadata.get("app_id") or agent_name),
                    session_id=str(query.metadata.get("session_id") or ""),
                    permissions=permissions,
                ),
                action="execute",
                resource=AccessResource("llm", "external_provider", owner_agent=agent_name),
                irreversible=True,
                reason="external LLM provider call",
            )
        )
        if decision.allowed:
            return None
        return KernelResponse.error(
            decision.error_code,
            metadata={
                "reason": decision.reason,
                "requires_intervention": decision.requires_intervention,
                "intervention_id": decision.intervention_id,
            },
        )

    def _audit_provider_result(
        self,
        query: LLMQuery,
        config: LLMConfig | None,
        response: KernelResponse,
        **metadata: Any,
    ) -> None:
        if self.event_sink is None:
            return
        self.event_sink.emit(
            "llm.audit",
            action=query.action_type or _action_type_from_operation(query.operation_type),
            operation_type=query.operation_type,
            request_id=query.request_id,
            provider_name=config.name if config is not None else "",
            backend=config.backend if config is not None else "",
            success=response.success is True,
            error_code=response.error_code,
            external_provider=config.backend if config is not None else "",
            **metadata,
        )

    def _audit_cancel_result(self, call_id: str, response: KernelResponse) -> None:
        if self.event_sink is None:
            return
        self.event_sink.emit(
            "llm.audit",
            action="cancel",
            operation_type="llm_cancel",
            call_id=call_id,
            success=response.success is True,
            error_code=response.error_code,
            external_provider="",
        )

    def _audit_status_result(self, call_id: str, result: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        self.event_sink.emit(
            "llm.audit",
            action="status",
            operation_type="llm_status",
            call_id=call_id,
            success=result.get("success") is True,
            error_code=str(result.get("error_code") or ""),
            external_provider="",
        )


def response_text(response: KernelResponse) -> str:
    message: Any = response.response_message
    if isinstance(message, dict):
        return str(message.get("content") or message.get("text") or message)
    return str(message or "")


def _normalize_batch_length(responses: list[KernelResponse], expected: int) -> list[KernelResponse]:
    if len(responses) >= expected:
        return responses[:expected]
    missing = [KernelResponse.error(LLMCoreErrorCode.RESPONSE_INVALID, metadata={"reason": "missing batch response"})]
    return responses + missing * (expected - len(responses))


def _action_type_from_operation(operation_type: str) -> str:
    if operation_type in {"llm_embed", "embed"}:
        return "embed"
    if operation_type in {"llm_complete", "complete"}:
        return "complete"
    return "chat"


def _cancel_call_id(params: dict[str, Any]) -> str:
    return str(params.get("call_id") or params.get("syscall_id") or params.get("correlation_id") or "")
