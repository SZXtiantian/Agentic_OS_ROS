from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class RunAppRequest:
    place: str = "厨房"
    wait: bool = True

    def to_dict(self) -> dict:
        return asdict(self)
