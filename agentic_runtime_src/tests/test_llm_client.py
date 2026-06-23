import json
import urllib.error

import pytest

from agentic_runtime.llm import LLMChat, LLMConfig, LLMError, OpenAICompatibleChatClient, load_llm_config


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_llm_config_loads_yunwu_without_source_secret(tmp_path, monkeypatch):
    config_path = tmp_path / "models.yaml"
    secret_path = tmp_path / "yunwu.env"
    config_path.write_text(
        """
models:
  default_reasoning_model:
    provider: yunwu
    base_url: https://yunwu.ai/v1/chat/completions
    model: custom-model
    timeout_s: 9
    temperature: 0
    max_tokens: 123
    enabled: true
""",
        encoding="utf-8",
    )
    secret_path.write_text("AGENTIC_LLM_API_KEY=test-secret\n", encoding="utf-8")
    monkeypatch.setenv("AGENTIC_LLM_MODEL", "env-model")

    config = load_llm_config(config_path=config_path, secret_path=secret_path)

    assert config.provider == "yunwu"
    assert config.base_url == "https://yunwu.ai/v1"
    assert config.model == "env-model"
    assert config.timeout_s == 9
    assert config.max_tokens == 123
    assert config.api_key == "test-secret"


def test_llm_config_without_provider_fields_is_unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTIC_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("AGENTIC_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("AGENTIC_LLM_MODEL", raising=False)
    monkeypatch.delenv("AGENTIC_LLM_API_KEY", raising=False)
    config_path = tmp_path / "models.yaml"
    config_path.write_text("models: {}\n", encoding="utf-8")

    config = load_llm_config(config_path=config_path, secret_path=tmp_path / "missing-secret.env")

    assert config.provider == "openai_compatible"
    assert config.base_url == ""
    assert config.model == ""
    with pytest.raises(LLMError) as exc:
        config.require_ready()
    assert exc.value.code == "LLM_PROVIDER_UNCONFIGURED"
    assert "base_url" in exc.value.reason
    assert "api_key" in exc.value.reason
    assert "model" in exc.value.reason


def test_openai_compatible_client_posts_chat_completion_and_parses_object(monkeypatch):
    config = LLMConfig(api_key="test-key", base_url="https://example.test/v1", model="gpt-4o-mini")
    client = OpenAICompatibleChatClient(config=config)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr("agentic_runtime.llm.client.urllib.request.urlopen", fake_urlopen)

    result = client.chat_json(system_prompt="system", user_prompt="user")

    assert result == {"ok": True}
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["timeout"] == config.timeout_s
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert captured["body"]["temperature"] == 0.0


def test_llmchat_facade_delegates_provider_client():
    class FakeClient:
        def chat_json(self, *, system_prompt, user_prompt):
            return {"system": system_prompt, "user": user_prompt}

    result = LLMChat(client=FakeClient()).chat_json(system_prompt="system", user_prompt="user")

    assert result == {"system": "system", "user": "user"}


def test_llm_client_rejects_markdown_fenced_json(monkeypatch):
    client = OpenAICompatibleChatClient(config=LLMConfig(api_key="test-key", base_url="https://example.test/v1", model="gpt-4o-mini"))

    def fake_urlopen(request, timeout):
        return _FakeResponse({"choices": [{"message": {"content": "```json\n{\"ok\": true}\n```"}}]})

    monkeypatch.setattr("agentic_runtime.llm.client.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(LLMError) as exc:
        client.chat_json(system_prompt="system", user_prompt="user")

    assert exc.value.code == "LLM_OUTPUT_MARKDOWN"


def test_llm_client_returns_structured_provider_error_for_network_failure(monkeypatch):
    client = OpenAICompatibleChatClient(config=LLMConfig(api_key="test-key", base_url="https://example.test/v1", model="gpt-4o-mini"))

    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("agentic_runtime.llm.client.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(LLMError) as exc:
        client.chat_json(system_prompt="system", user_prompt="user")

    assert exc.value.code == "LLM_PROVIDER_ERROR"


def test_llm_client_returns_structured_provider_error_for_http_failure(monkeypatch):
    client = OpenAICompatibleChatClient(config=LLMConfig(api_key="test-key", base_url="https://example.test/v1", model="gpt-4o-mini"))

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr("agentic_runtime.llm.client.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(LLMError) as exc:
        client.chat_json(system_prompt="system", user_prompt="user")

    assert exc.value.code == "LLM_PROVIDER_ERROR"
    assert "503" in exc.value.reason
