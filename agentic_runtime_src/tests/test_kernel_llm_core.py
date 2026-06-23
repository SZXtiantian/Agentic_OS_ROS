from __future__ import annotations

import sys
import threading
import types
import urllib.error

from agentic_os.kernel.access import AccessManager, AlwaysAllowTestInterventionProvider
from agentic_os.kernel.hooks import InMemoryKernelEventSink
from agentic_os.kernel.llm_core import (
    HuggingFaceProvider,
    LLMAdapter,
    LLMConfig,
    LLMCoreErrorCode,
    LiteLLMProvider,
    OpenAICompatibleProvider,
    SmartRouting,
    normalize_openai_response,
)
from agentic_os.kernel.model_library import ModelEndpoint, ModelLibrary
from agentic_os.kernel.system_call import KernelResponse, LLMQuery, create_syscall


class RecordingProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.queries: list[LLMQuery] = []

    def complete(self, query: LLMQuery) -> KernelResponse:
        self.queries.append(query)
        return KernelResponse(True, response_message={"model": self.name, "tools": query.tools})


class FailingProvider:
    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse.error(LLMCoreErrorCode.REQUEST_FAILED)


class JSONProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse.ok({"role": "assistant", "content": self.content})


class BatchLLMProvider:
    def __init__(self) -> None:
        self.batches: list[list[LLMQuery]] = []

    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse.ok({"single": True})

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        self.batches.append(list(queries))
        return [KernelResponse.ok({"index": index}) for index, _query in enumerate(queries)]


class PartialFailureBatchProvider(BatchLLMProvider):
    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        self.batches.append(list(queries))
        return [
            KernelResponse.ok({"index": 0}),
            KernelResponse.error("LLM_SINGLE_QUERY_FAILED"),
            KernelResponse.ok({"index": 2}),
        ]


class BlockingProvider:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete(self, query: LLMQuery) -> KernelResponse:
        self.entered.set()
        self.release.wait(timeout=2.0)
        return KernelResponse.ok({"content": "late response"})


def test_llm_adapter_routes_sequentially():
    provider_a = RecordingProvider("model-a")
    provider_b = RecordingProvider("model-b")
    adapter = LLMAdapter(
        [
            LLMConfig(name="model-a", backend="openai_compatible"),
            LLMConfig(name="model-b", backend="openai_compatible"),
        ],
        providers={"model-a": provider_a, "model-b": provider_b},
    )

    first = adapter.complete(LLMQuery(operation_type="chat"))
    second = adapter.complete(LLMQuery(operation_type="chat"))

    assert first.response_message["model"] == "model-a"
    assert second.response_message["model"] == "model-b"


def test_llm_adapter_uses_injected_provider_without_network():
    provider = RecordingProvider("offline")
    adapter = LLMAdapter([LLMConfig(name="offline", backend="openai_compatible")], providers={"offline": provider})
    query = LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hi"}])

    response = adapter.complete(query)

    assert response.success is True
    assert provider.queries == [query]


def test_llm_adapter_emits_provider_audit_without_prompt_leak():
    sink = InMemoryKernelEventSink()
    provider = RecordingProvider("audited")
    adapter = LLMAdapter(
        [LLMConfig(name="audited", backend="openai_compatible")],
        providers={"audited": provider},
        event_sink=sink,
    )
    query = LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "secret prompt"}])

    response = adapter.complete(query)

    assert response.success is True
    events = [event for event in sink.recent(limit=5) if event["event_type"] == "llm.audit"]
    assert events[-1]["metadata"]["provider_name"] == "audited"
    assert events[-1]["metadata"]["backend"] == "openai_compatible"
    assert events[-1]["metadata"]["success"] is True
    assert "secret prompt" not in str(events)


def test_llm_adapter_batch_preserves_order():
    provider = BatchLLMProvider()
    adapter = LLMAdapter([LLMConfig(name="batch", backend="openai_compatible")], providers={"batch": provider})

    responses = adapter.complete_batch([LLMQuery(operation_type="chat") for _ in range(3)])

    assert [response.response_message["index"] for response in responses] == [0, 1, 2]
    assert len(provider.batches) == 1


def test_llm_adapter_batch_single_failure_does_not_fail_whole_batch():
    provider = PartialFailureBatchProvider()
    adapter = LLMAdapter([LLMConfig(name="batch", backend="openai_compatible")], providers={"batch": provider})

    responses = adapter.complete_batch([LLMQuery(operation_type="chat") for _ in range(3)])

    assert [response.success for response in responses] == [True, False, True]
    assert responses[1].error_code == "LLM_SINGLE_QUERY_FAILED"


def test_llm_adapter_batch_falls_back_to_sequential_complete():
    provider = RecordingProvider("sequential")
    adapter = LLMAdapter([LLMConfig(name="sequential", backend="openai_compatible")], providers={"sequential": provider})
    queries = [LLMQuery(operation_type="chat") for _ in range(2)]

    responses = adapter.complete_batch(queries)

    assert [response.success for response in responses] == [True, True]
    assert provider.queries == queries


def test_llm_adapter_returns_error_for_missing_provider():
    adapter = LLMAdapter([LLMConfig(name="x", backend="unknown_backend")])

    response = adapter.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNAVAILABLE


def test_optional_litellm_dependency_missing_is_structured():
    provider = LiteLLMProvider(LLMConfig(name="x", backend="litellm", model="real-model"))

    response = provider.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code in {LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING, LLMCoreErrorCode.PROVIDER_ERROR}


def test_litellm_provider_embed_uses_real_embedding_api(monkeypatch):
    calls = {}

    def embedding(**kwargs):
        calls["embedding"] = kwargs
        return {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}], "model": kwargs["model"]}

    def completion(**kwargs):
        raise AssertionError("embed requests must not use chat completion")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=embedding, completion=completion))
    provider = LiteLLMProvider(LLMConfig(name="x", backend="litellm", model="embedding-model", timeout_s=7))

    response = provider.complete(LLMQuery(operation_type="llm_embed", params={"texts": ["alpha", "beta"]}, action_type="embed"))

    assert response.success is True
    assert response.response_message["embeddings"] == [[0.1, 0.2], [0.3, 0.4]]
    assert response.response_message["model"] == "embedding-model"
    assert response.metadata["provider"] == "x"
    assert calls["embedding"] == {"model": "embedding-model", "input": ["alpha", "beta"], "timeout": 7}


def test_litellm_provider_embed_remote_failure_is_structured(monkeypatch):
    def embedding(**kwargs):
        raise RuntimeError("provider offline")

    monkeypatch.setitem(sys.modules, "litellm", types.SimpleNamespace(embedding=embedding))
    provider = LiteLLMProvider(LLMConfig(name="x", backend="litellm", model="embedding-model"))

    response = provider.complete(LLMQuery(operation_type="llm_embed", params={"text": "alpha"}, action_type="embed"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_ERROR
    assert "provider offline" in response.metadata["reason"]


def test_optional_huggingface_dependency_missing_is_structured():
    provider = HuggingFaceProvider(LLMConfig(name="x", backend="huggingface", model="real-model"))

    response = provider.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code in {LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING, LLMCoreErrorCode.PROVIDER_UNCONFIGURED}


def test_openai_response_normalization_includes_tool_calls():
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "use tool",
                    "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "math.add"}}],
                }
            }
        ]
    }

    normalized = normalize_openai_response(body)

    assert normalized.role == "assistant"
    assert normalized.content == "use tool"
    assert normalized.tool_calls[0]["function"]["name"] == "math.add"


def test_json_response_valid_and_invalid_are_normalized():
    valid = LLMAdapter([LLMConfig(name="json", backend="openai_compatible")], providers={"json": JSONProvider('{"ok": true}')})
    invalid = LLMAdapter([LLMConfig(name="json", backend="openai_compatible")], providers={"json": JSONProvider("{bad")})
    query = LLMQuery(operation_type="chat", response_format={"type": "json_object"})

    valid_response = valid.complete(query)
    invalid_response = invalid.complete(query)

    assert valid_response.success is True
    assert valid_response.metadata["json"] == {"ok": True}
    assert invalid_response.success is False
    assert invalid_response.error_code == LLMCoreErrorCode.RESPONSE_JSON_INVALID
    assert invalid_response.metadata["raw_text"] == "{bad"


def test_selected_llms_and_fallback_candidates_work():
    failing = FailingProvider()
    good = RecordingProvider("good")
    adapter = LLMAdapter(
        [
            LLMConfig(name="bad", backend="openai_compatible"),
            LLMConfig(name="good", backend="openai_compatible"),
        ],
        providers={"bad": failing, "good": good},
    )

    selected = adapter.complete(LLMQuery(operation_type="chat", selected_llms=["good"]))
    fallback = adapter.complete(LLMQuery(operation_type="chat"))

    assert selected.success is True
    assert selected.response_message["model"] == "good"
    assert fallback.success is True
    assert fallback.response_message["model"] == "good"


def test_smart_routing_sorts_by_quality_then_cost():
    router = SmartRouting(
        [
            LLMConfig(name="cheap", backend="openai_compatible", quality_score=0.5, cost_per_1k_input=0.1),
            LLMConfig(name="best", backend="openai_compatible", quality_score=0.9, cost_per_1k_input=1.0),
            LLMConfig(name="mid", backend="openai_compatible", quality_score=0.5, cost_per_1k_input=0.05),
        ]
    )

    assert [config.name for config in router.candidates()] == ["best", "mid", "cheap"]


def test_llm_query_with_json_response_format_preserved():
    provider = RecordingProvider("configured")
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": provider})
    query = LLMQuery(
        operation_type="chat",
        messages=[{"role": "user", "content": "return json"}],
        response_format={"type": "json_object"},
    )

    response = adapter.complete(query)

    assert response.success is True
    assert provider.queries[0].response_format == {"type": "json_object"}


def test_llm_query_with_tools_preserved():
    provider = RecordingProvider("configured")
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": provider})
    query = LLMQuery(
        operation_type="chat",
        tools=[{"type": "function", "function": {"name": "calculator.add"}}],
    )

    response = adapter.complete(query)

    assert response.success is True
    assert provider.queries[0].tools == query.tools


def test_llm_adapter_address_request_accepts_llm_syscall():
    provider = RecordingProvider("configured")
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": provider})
    syscall = create_syscall(
        "agent_a",
        LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hello"}]),
    )

    response = adapter.address_request(syscall)

    assert response.success is True
    assert response.metadata["model"] == "configured"


def test_llm_external_call_requires_explicit_permission_before_provider_call():
    sink = InMemoryKernelEventSink()
    provider = RecordingProvider("configured")
    adapter = LLMAdapter(
        [
            LLMConfig(
                name="configured",
                backend="openai_compatible",
                hostname="https://example.test/v1",
                api_key="test-key",
                model="real-model",
            )
        ],
        providers={"configured": provider},
        access_manager=AccessManager(event_sink=sink),
        event_sink=sink,
    )
    syscall = create_syscall("agent_a", LLMQuery(operation_type="chat"))

    response = adapter.address_request(syscall)

    assert response.success is False
    assert response.error_code == "ACCESS_DENIED"
    assert provider.queries == []
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "llm.audit"][-1]
    assert audit["metadata"]["error_code"] == "ACCESS_DENIED"
    assert audit["metadata"]["access_gate"] is True


def test_llm_external_call_requires_access_manager_before_provider_call():
    sink = InMemoryKernelEventSink()
    provider = RecordingProvider("configured")
    adapter = LLMAdapter(
        [
            LLMConfig(
                name="configured",
                backend="openai_compatible",
                hostname="https://example.test/v1",
                api_key="test-key",
                model="real-model",
            )
        ],
        providers={"configured": provider},
        event_sink=sink,
    )
    syscall = create_syscall(
        "agent_a",
        LLMQuery(operation_type="chat", metadata={"permissions": ["llm.external.call"]}),
    )

    response = adapter.address_request(syscall)

    assert response.success is False
    assert response.error_code == "ACCESS_MANAGER_UNAVAILABLE"
    assert provider.queries == []
    audit = [event for event in sink.recent(limit=10) if event["event_type"] == "llm.audit"][-1]
    assert audit["metadata"]["error_code"] == "ACCESS_MANAGER_UNAVAILABLE"
    assert audit["metadata"]["access_gate"] is True


def test_llm_external_call_with_permission_requires_intervention_by_default():
    sink = InMemoryKernelEventSink()
    provider = RecordingProvider("configured")
    adapter = LLMAdapter(
        [
            LLMConfig(
                name="configured",
                backend="openai_compatible",
                hostname="https://example.test/v1",
                api_key="test-key",
                model="real-model",
            )
        ],
        providers={"configured": provider},
        access_manager=AccessManager(event_sink=sink),
        event_sink=sink,
    )
    syscall = create_syscall(
        "agent_a",
        LLMQuery(operation_type="chat", metadata={"permissions": ["llm.external.call"]}),
    )

    response = adapter.address_request(syscall)

    assert response.success is False
    assert response.error_code == "ACCESS_INTERVENTION_REQUIRED"
    assert provider.queries == []
    assert any(
        event["event_type"] == "access.checked" and event["metadata"]["requires_intervention"] is True
        for event in sink.recent(limit=10)
    )


def test_llm_external_call_runs_after_operator_intervention_allows():
    sink = InMemoryKernelEventSink()
    provider = RecordingProvider("configured")
    access = AccessManager(intervention_provider=AlwaysAllowTestInterventionProvider(), event_sink=sink)
    adapter = LLMAdapter(
        [
            LLMConfig(
                name="configured",
                backend="openai_compatible",
                hostname="https://example.test/v1",
                api_key="test-key",
                model="real-model",
            )
        ],
        providers={"configured": provider},
        access_manager=access,
        event_sink=sink,
    )
    query = LLMQuery(operation_type="chat", metadata={"permissions": ["llm.external.call"]})

    response = adapter.address_request(create_syscall("agent_a", query))

    assert response.success is True
    assert provider.queries == [query]
    assert any(event["event_type"] == "access.checked" for event in sink.recent(limit=10))


def test_llm_adapter_without_real_provider_fails_unavailable():
    adapter = LLMAdapter([LLMConfig(name="disabled", backend="mock")], providers={"disabled": RecordingProvider("disabled")})

    response = adapter.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNAVAILABLE
    assert response.metadata["backend"] == "mock"


def test_llm_adapter_cancel_missing_call_returns_syscall_not_found():
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": RecordingProvider("configured")})
    syscall = create_syscall("agent_a", LLMQuery(operation_type="cancel", params={"call_id": "missing"}))

    response = adapter.address_request(syscall)

    assert response.success is False
    assert response.error_code == "SYSCALL_NOT_FOUND"


def test_llm_adapter_can_cancel_active_syscall_by_id():
    provider = BlockingProvider()
    adapter = LLMAdapter([LLMConfig(name="blocking", backend="openai_compatible")], providers={"blocking": provider})
    syscall = create_syscall("agent_a", LLMQuery(operation_type="chat"))
    result: dict[str, KernelResponse] = {}

    thread = threading.Thread(target=lambda: result.setdefault("response", adapter.address_request(syscall)))
    thread.start()
    assert provider.entered.wait(timeout=1.0)
    assert syscall.syscall_id in adapter.status()["active"]

    cancel = adapter.address_request(create_syscall("agent_a", LLMQuery(operation_type="cancel", params={"call_id": syscall.syscall_id})))
    provider.release.set()
    thread.join(timeout=1.0)

    assert cancel.success is True
    assert result["response"].success is False
    assert result["response"].error_code == LLMCoreErrorCode.CANCELLED
    assert adapter.status()["active"] == []


def test_llm_adapter_batch_handles_cancel_without_provider_call():
    provider = RecordingProvider("configured")
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": provider})
    syscall = create_syscall("agent_a", LLMQuery(operation_type="cancel", params={"call_id": "missing"}))

    response = adapter.address_batch([syscall])[0]

    assert response.success is False
    assert response.error_code == "SYSCALL_NOT_FOUND"
    assert provider.queries == []


def test_llm_status_reports_unconfigured_openai_provider():
    adapter = LLMAdapter([LLMConfig(name="needs_config", backend="openai_compatible")])

    status = adapter.status()

    assert status["state"] == "unavailable"
    assert status["providers"][0]["error_code"] == LLMCoreErrorCode.PROVIDER_UNCONFIGURED
    assert "base_url" in status["providers"][0]["reason"]
    assert "api_key" in status["providers"][0]["reason"]
    assert "model" in status["providers"][0]["reason"]


def test_llm_status_requires_explicit_model_for_configured_openai_provider():
    adapter = LLMAdapter(
        [
            LLMConfig(
                name="needs-model",
                backend="openai_compatible",
                hostname="https://example.test/v1",
                api_key="test-key",
            )
        ]
    )

    status = adapter.status()

    assert status["state"] == "unavailable"
    assert status["providers"][0]["error_code"] == LLMCoreErrorCode.PROVIDER_UNCONFIGURED
    assert "model" in status["providers"][0]["reason"]


def test_openai_provider_missing_config_returns_unconfigured():
    provider = OpenAICompatibleProvider(LLMConfig(name="needs_config", backend="openai_compatible"))

    response = provider.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNCONFIGURED


def test_openai_provider_missing_model_returns_unconfigured_without_network(monkeypatch):
    provider = OpenAICompatibleProvider(
        LLMConfig(name="needs-model", backend="openai_compatible", hostname="https://example.test/v1", api_key="test-key")
    )
    called = False

    def urlopen_should_not_run(request, timeout):
        nonlocal called
        called = True
        raise AssertionError("provider must fail before network without model")

    monkeypatch.setattr("agentic_os.kernel.llm_core.provider.urllib.request.urlopen", urlopen_should_not_run)

    response = provider.complete(LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hi"}]))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNCONFIGURED
    assert response.metadata["required_config"] == ["model"]
    assert called is False


def test_openai_provider_remote_failure_returns_provider_error(monkeypatch):
    provider = OpenAICompatibleProvider(
        LLMConfig(
            name="configured",
            backend="openai_compatible",
            hostname="https://example.test/v1",
            api_key="test-key",
            model="real-model",
        )
    )

    def raise_url_error(request, timeout):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("agentic_os.kernel.llm_core.provider.urllib.request.urlopen", raise_url_error)

    response = provider.complete(LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hi"}]))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_ERROR


def test_model_library_router_backward_compatible():
    models = ModelLibrary([ModelEndpoint(name="real-vla", provider="openai_compatible", capabilities=("chat", "vla"))])

    routed = models.route("vla")

    assert routed["success"] is True
    assert routed["endpoint"]["name"] == "real-vla"
