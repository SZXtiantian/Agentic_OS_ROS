from __future__ import annotations

from agentic_os.kernel.llm_core import LLMAdapter, LLMConfig, LLMCoreErrorCode
from agentic_os.kernel.model_library import ModelEndpoint, ModelLibrary
from agentic_os.kernel.system_call import KernelResponse, LLMQuery, create_syscall


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.queries: list[LLMQuery] = []

    def complete(self, query: LLMQuery) -> KernelResponse:
        self.queries.append(query)
        return KernelResponse(True, response_message={"model": self.name, "tools": query.tools})


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


def test_llm_adapter_returns_error_for_missing_provider():
    adapter = LLMAdapter([LLMConfig(name="x", backend="unknown_backend")])

    response = adapter.complete(LLMQuery(operation_type="chat"))

    assert response.success is False
    assert response.error_code == LLMCoreErrorCode.PROVIDER_UNSUPPORTED


def test_llm_query_with_json_response_format_preserved():
    adapter = LLMAdapter([LLMConfig(name="mock", backend="mock")])
    query = LLMQuery(
        operation_type="chat",
        messages=[{"role": "user", "content": "return json"}],
        response_format={"type": "json_object"},
    )

    response = adapter.complete(query)

    assert response.success is True
    assert response.response_message["response_format"] == {"type": "json_object"}


def test_llm_query_with_tools_preserved():
    adapter = LLMAdapter([LLMConfig(name="mock", backend="mock")])
    query = LLMQuery(
        operation_type="chat",
        tools=[{"type": "function", "function": {"name": "calculator.add"}}],
    )

    response = adapter.complete(query)

    assert response.success is True
    assert response.response_message["tools"] == query.tools


def test_llm_adapter_address_request_accepts_llm_syscall():
    adapter = LLMAdapter([LLMConfig(name="mock", backend="mock")])
    syscall = create_syscall(
        "agent_a",
        LLMQuery(operation_type="chat", messages=[{"role": "user", "content": "hello"}]),
    )

    response = adapter.address_request(syscall)

    assert response.success is True
    assert response.metadata["model"] == "mock"


def test_model_library_router_backward_compatible():
    models = ModelLibrary([ModelEndpoint(name="mock-vla", provider="mock", capabilities=("chat", "vla"))])

    routed = models.route("vla")

    assert routed["success"] is True
    assert routed["endpoint"]["name"] == "mock-vla"
