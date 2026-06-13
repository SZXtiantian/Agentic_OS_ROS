from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ConfigRefreshResult:
    success: bool
    reloaded: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_code: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
