from __future__ import annotations

import re

from .embeddings import EmbeddingProvider, HashEmbeddingProvider, cosine_similarity
from .note import MemoryNote


class LexicalMemoryRetriever:
    def retrieve(self, notes: list[MemoryNote], query: str, limit: int = 5) -> list[MemoryNote]:
        query_text = str(query).lower()
        if not query_text:
            return notes[:limit]
        tokens = [token for token in re.findall(r"[\w\u4e00-\u9fff]+", query_text) if len(token) > 2]
        scored: list[tuple[int, MemoryNote]] = []
        for note in notes:
            haystacks = [
                str(note.content).lower(),
                note.context.lower(),
                note.category.lower(),
                " ".join(note.keywords).lower(),
                " ".join(note.tags).lower(),
            ]
            score = sum(1 for text in haystacks if query_text in text)
            if not score and tokens:
                score = sum(1 for text in haystacks for token in tokens if token in text)
            if score:
                scored.append((score, note))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [note for _score, note in scored[:limit]]

    def score(self, note: MemoryNote, query: str) -> float:
        return 1.0 if note in self.retrieve([note], query, limit=1) else 0.0


class HybridMemoryRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        lexical_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> None:
        self.embedding_provider = embedding_provider or HashEmbeddingProvider()
        self.lexical = LexicalMemoryRetriever()
        self.lexical_weight = lexical_weight
        self.vector_weight = vector_weight

    def retrieve(
        self,
        notes: list[MemoryNote],
        query: str,
        limit: int = 5,
        filters: dict[str, str] | None = None,
    ) -> list[MemoryNote]:
        filtered = [note for note in notes if _matches_filters(note, filters or {})]
        query_vector = self.embedding_provider.embed(query)
        scored: list[tuple[float, MemoryNote]] = []
        for note in filtered:
            vector_score = cosine_similarity(query_vector, self.embedding_provider.embed(str(note.content)))
            lexical_score = self.lexical.score(note, query)
            score = self.lexical_weight * lexical_score + self.vector_weight * vector_score
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [note for _score, note in scored[:limit]]


def _matches_filters(note: MemoryNote, filters: dict[str, str]) -> bool:
    robot = dict(note.metadata.get("robot") or {})
    values = {**{key: str(value) for key, value in note.metadata.items() if not isinstance(value, dict)}, **robot}
    for key in ("place_id", "robot_id", "frame_id", "retention_class", "privacy"):
        expected = filters.get(key)
        if expected is not None and str(values.get(key, "")) != str(expected):
            return False
    return True
