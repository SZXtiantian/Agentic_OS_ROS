from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class ArtifactRecord:
    session_id: str
    name: str
    artifact_type: str
    path: str
    size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)
