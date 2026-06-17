from __future__ import annotations


class LSFSAdapter:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def status(self) -> dict[str, object]:
        return {"enabled": self.enabled, "implemented": False}
