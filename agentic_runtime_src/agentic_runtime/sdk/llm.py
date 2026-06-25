from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_runtime.llm.errors import LLMError


@dataclass
class LLMJSONResult:
    success: bool
    plan: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "plan": dict(self.plan),
            "error_code": self.error_code,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


class LLMAPI:
    """Runtime-owned LLM facade for Agent Apps.

    Agent Apps call this SDK surface instead of constructing provider clients or
    reading provider secrets. The actual provider client remains owned by
    RuntimeServer.llm_chat.
    """

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def chat_json(self, *, system_prompt: str, user_prompt: str, timeout_s: int | None = None) -> LLMJSONResult:
        del timeout_s
        runtime_server = getattr(getattr(self.ctx, "kernel_service", None), "runtime_server", None)
        llm_chat = getattr(runtime_server, "llm_chat", None)
        if llm_chat is None or not hasattr(llm_chat, "chat_json"):
            return LLMJSONResult(
                success=False,
                error_code="LLMCHAT_UNAVAILABLE",
                reason="RuntimeServer.llm_chat is not available on this AgentContext",
                metadata={"facade": "agentic_runtime.sdk.LLMAPI", "provider_owner": "RuntimeServer"},
            )
        try:
            plan = llm_chat.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        except LLMError as exc:
            return LLMJSONResult(
                success=False,
                error_code=exc.code,
                reason=exc.reason,
                metadata={"facade": "agentic_runtime.sdk.LLMAPI", "provider_owner": "RuntimeServer"},
            )
        except Exception as exc:
            return LLMJSONResult(
                success=False,
                error_code="LLMCHAT_UNAVAILABLE",
                reason=str(exc),
                metadata={"facade": "agentic_runtime.sdk.LLMAPI", "provider_owner": "RuntimeServer"},
            )
        if not isinstance(plan, dict):
            return LLMJSONResult(
                success=False,
                error_code="LLM_RESPONSE_INVALID",
                reason=f"RuntimeServer.llm_chat returned {type(plan).__name__}, expected dict",
                metadata={"facade": "agentic_runtime.sdk.LLMAPI", "provider_owner": "RuntimeServer"},
            )
        return LLMJSONResult(
            success=True,
            plan=dict(plan),
            metadata={"facade": "agentic_runtime.sdk.LLMAPI", "provider_owner": "RuntimeServer"},
        )
