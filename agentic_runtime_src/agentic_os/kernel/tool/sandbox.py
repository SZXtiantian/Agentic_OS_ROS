from __future__ import annotations


class ToolSandboxPolicy:
    def __init__(self, network: bool = False, filesystem: bool = False) -> None:
        self.network = network
        self.filesystem = filesystem

    def to_dict(self) -> dict[str, bool]:
        return {"network": self.network, "filesystem": self.filesystem}
