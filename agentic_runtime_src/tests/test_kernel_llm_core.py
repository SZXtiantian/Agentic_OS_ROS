from __future__ import annotations

from agentic_os.kernel.llm_core import (
    HuggingFaceProvider,
    LLMAdapter,
    LLMConfig,
    LLMCoreErrorCode,
    LiteLLMProvider,
    SmartRouting,
    normalize_openai_response,
)
from agentic_os.kernel.model_library import ModelEndpoint, ModelLibrary
from agentic_os.kernel.system_call import KernelResponse, LLMQuery, create_syscall


class FakeProvider:
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


class FakeBatchLLMProvider:
    def __init__(self) -> None:
        self.batches: list[list[LLMQuery]] = []

    def complete(self, query: LLMQuery) -> KernelResponse:
        return KernelResponse.ok({"single": True})

    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        self.batches.append(list(queries))
        return [KernelResponse.ok({"index": index}) for index, _query in enumerate(queries)]


class FakePartialFailureBatchProvider(FakeBatchLLMProvider):
    def complete_batch(self, queries: list[LLMQuery]) -> list[KernelResponse]:
        self.batches.append(list(queries))
        return [
            KernelResponse.ok({"index": 0}),
            KernelResponse.error("LLM_SINGLE_QUERY_FAILED"),
            KernelResponse.ok({"index": 2}),
        ]


def test_llm_adapter_routes_sequentially():
    provider_a = FakeProvider("mock-a")
    provider_b = FakeProvider("mock-b")
    adapter = LLMAdapter(
        [
            LLMConfig(name="mock-a", backend="mock"),
            LLMConfig(name="mock-b", backend="mock"),
        ],
        providers={"mock-a": provider_a, "mock-b": provider_b},
    )

    first = adapter.complete(LLMQuery(operation_type="chat"))
    second = adapter.complete(LLMQuery(operation_type="chat"))

    assert first.response_message["model"] == "mock-a"
    assert second.response_message["model"] == "mock-b"


def test_llm_adapter_uses_fake_provider_without_network():
    provider = FakeProvider("offline")
    adapter = LLMAdapter([LLMConfig(name="offline", backend="mock")], providers={"offline": provider})
    query = LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hi"}])

    response = adapter.complete(query)

    assert response.success is True
    assert provider.queries == [query]


def test_llm_adapter_batch_preserves_order():
    provider = FakeBatchLLMProvider()
    adapter = LLMAdapter([LLMConfig(name="batch", backend="mock")], providers={"batch": provider})

    responses = adapter.complete_batch([LLMQuery(operation_type="chat") for _ in range(3)])

    assert [response.response_message["index"] for response in responses] == [0, 1, 2]
    assert len(provider.batches) == 1


def test_llm_adapter_batch_single_failure_does_not_fail_whole_batch():
    provider = FakePartialFailureBatchProvider()
    adapter = LLMAdapter([LLMConfig(name="batch", backend="mock")], providers={"batch": provider})

    responses = adapter.complete_batch([LLMQuery(operation_type="chat") for _ in range(3)])

    assert [response.success for response in responses] == [True, False, True]
    assert responses[1].error_code == "LLM_SINGLE_QUERY_FAILED"


def test_llm_adapter_batch_falls_back_to_sequential_complete():
    provider = FakeProvider("sequential")
    adapter = LLMAdapter([LLMConfig(name="sequential", backend="mock")], providers={"sequential": provider})
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
    provider = LiteLLMProvider(LLMConfig(name="x", backend="litellm"))

    response = provider.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code in {LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING, LLMCoreErrorCode.REQUEST_FAILED}


def test_optional_huggingface_dependency_missing_is_structured():
    provider = HuggingFaceProvider(LLMConfig(name="x", backend="huggingface"))

    response = provider.complete(LLMQuery(operation_type="chat"))

    assert response.success in {True, False}
    if not response.success:
        assert response.error_code == LLMCoreErrorCode.PROVIDER_DEPENDENCY_MISSING


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
    valid = LLMAdapter([LLMConfig(name="json", backend="mock")], providers={"json": JSONProvider('{"ok": true}')})
    invalid = LLMAdapter([LLMConfig(name="json", backend="mock")], providers={"json": JSONProvider("{bad")})
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
    good = FakeProvider("good")
    adapter = LLMAdapter(
        [
            LLMConfig(name="bad", backend="mock"),
            LLMConfig(name="good", backend="mock"),
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
            LLMConfig(name="cheap", backend="mock", quality_score=0.5, cost_per_1k_input=0.1),
            LLMConfig(name="best", backend="mock", quality_score=0.9, cost_per_1k_input=1.0),
            LLMConfig(name="mid", backend="mock", quality_score=0.5, cost_per_1k_input=0.05),
        ]
    )

    assert [config.name for config in router.candidates()] == ["best", "mid", "cheap"]


def test_llm_query_with_json_response_format_preserved():
    provider = FakeProvider("configured")
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
    provider = FakeProvider("configured")
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": provider})
    query = LLMQuery(
        operation_type="chat",
        tools=[{"type": "function", "function": {"name": "calculator.add"}}],
    )

    response = adapter.complete(query)

    assert response.success is True
    assert provider.queries[0].tools == query.tools


def test_llm_adapter_address_request_accepts_llm_syscall():
    provider = FakeProvider("configured")
    adapter = LLMAdapter([LLMConfig(name="configured", backend="openai_compatible")], providers={"configured": provider})
    syscall = create_syscall(
        "agent_a",
        LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hello"}]),
    )

    response = adapter.address_request(syscall)

    assert response.success is True
    assert response.metadata["model"] == "configured"


def test_llm_adapter_without_real_provider_fails_unavailable():
    adapter = LLMAdapter([LLMConfig(name="disabled", backend="mock")])

    response = adapter.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNAVAILABLE


def test_model_library_router_backward_compatible():
    models = ModelLibrary([ModelEndpoint(name="mock-vla", provider="mock", capabilities=("chat", "vla"))])

    routed = models.route("vla")

    assert routed["success"] is True
    assert routed["endpoint"]["name"] == "mock-vla"
