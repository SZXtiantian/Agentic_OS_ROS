from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReuseEdge:
    producer_node_id: str
    consumer_node_id: str
    fact_key: str
    fact_id: str
    ttl_ok: bool
    confidence_ok: bool
    schema_ok: bool
    world_epoch_ok: bool
    source_real_ok: bool
    accepted: bool
    reject_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
