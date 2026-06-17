from __future__ import annotations

import re

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
