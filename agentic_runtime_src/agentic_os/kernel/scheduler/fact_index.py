from __future__ import annotations


class FactIndex:
    def __init__(self) -> None:
        self._producers: dict[str, set[str]] = {}
        self._consumers: dict[str, set[str]] = {}

    def index_node(self, node_id: str, *, produces: list[str], consumes: list[str]) -> None:
        for fact_key in produces:
            self._producers.setdefault(fact_key, set()).add(node_id)
        for fact_key in consumes:
            self._consumers.setdefault(fact_key, set()).add(node_id)

    def producers(self, fact_key: str) -> set[str]:
        return set(self._producers.get(fact_key, set()))

    def consumers(self, fact_key: str) -> set[str]:
        return set(self._consumers.get(fact_key, set()))

    def snapshot(self) -> dict[str, dict[str, list[str]]]:
        return {
            "producers": {key: sorted(value) for key, value in sorted(self._producers.items())},
            "consumers": {key: sorted(value) for key, value in sorted(self._consumers.items())},
        }
