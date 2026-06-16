from __future__ import annotations


class LLMError(RuntimeError):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.code, "reason": self.reason}
