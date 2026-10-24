"""Pluggable recall providers: lexical (default) and optional vector.

The public ``recall()`` function stays lexical. This module adds an explicit
provider interface so an embedding backend can be swapped in without changing
call sites:

    provider = make_provider("vector", embedder=my_embedder)
    block = provider.recall(query, rows=rows, user_id=uid)

No embedding model is bundled. Bring a callable batch embedder
``embedder(list[str]) -> list[list[float]]`` or the optional ONNX adapter.
"""
from __future__ import annotations

import hashlib
from typing import Callable, Protocol, Sequence

from .score import ScoredMemory, format_scored, recall as lexical_recall
from .store import RetrievalRow


class VectorUnavailableError(RuntimeError):
    """Vector backend requested without a usable embedder/model."""


Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


class BaseRecallProvider(Protocol):
    name: str

    def recall(
        self,
        query: str,
        *,
        rows: Sequence[RetrievalRow],
        context: str = "",
        group_id: str = "",
        user_id: str = "",
        top_k: int = 5,
        instruction: str = "",
        max_chars: int = 900,
    ) -> str: ...


class LexicalProvider:
    """The default zero-dependency scorer (anchor + instruction separation)."""

    name = "lexical"

    def recall(self, query, *, rows, context="", group_id="", user_id="", top_k=5, instruction="", max_chars=900):
        return lexical_recall(
            query,
            rows=rows,
            context=context,
            group_id=group_id,
            user_id=user_id,
            top_k=top_k,
            instruction=instruction,
            max_chars=max_chars,
        )


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise VectorUnavailableError("embedding dimensions differ: %d vs %d" % (len(a), len(b)))
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class VectorProvider:
    """Cosine-similarity recall over caller-supplied embeddings.

    The embedder is called in batches. Vectors are cached by ``(row.id,
    sha256(content))``; feed a deterministic embedder (or the ONNX adapter).
    ``context``/``instruction`` are accepted for API compatibility but vectors
    do not use them; keep anchor/instruction invariants in a post-filter if you
    need them.
    """

    name = "vector"

    def __init__(self, embedder: Embedder, *, cache: bool = True) -> None:
        if embedder is None:
            raise VectorUnavailableError("VectorProvider needs an embedder callable")
        self.embedder = embedder
        self.cache = cache
        self._vectors: dict[tuple[int, str], tuple[float, ...]] = {}

    def _key(self, row: RetrievalRow) -> tuple[int, str]:
        return row.id, hashlib.sha256(row.content.encode("utf-8")).hexdigest()

    def _embed_missing(self, rows: Sequence[RetrievalRow]) -> list[tuple[float, ...]]:
        missing = [row for row in rows if not self.cache or self._key(row) not in self._vectors]
        if missing:
            vectors = self.embedder([row.content for row in missing])
            if len(vectors) != len(missing):
                raise VectorUnavailableError("embedder returned %d vectors for %d texts" % (len(vectors), len(missing)))
            for row, vector in zip(missing, vectors):
                self._vectors[self._key(row)] = tuple(float(value) for value in vector)
        return [self._vectors[self._key(row)] for row in rows]

    def recall(self, query, *, rows, context="", group_id="", user_id="", top_k=5, instruction="", max_chars=900):
        rows = [row for row in rows if not user_id or not row.user_id or row.user_id == user_id]
        if not rows or not str(query or "").strip():
            return ""
        query_vector = tuple(float(value) for value in self.embedder([query])[0])
        row_vectors = self._embed_missing(rows)
        scored = []
        for row, vector in zip(rows, row_vectors):
            score = _cosine(query_vector, vector)
            if score > 0:
                scored.append(ScoredMemory(row=row, score=score, coverage=0.0, anchor_hit=False))
        scored.sort(key=lambda item: item.score, reverse=True)
        limit = max(1, int(top_k or 5))
        return format_scored(scored[:limit], max_chars=max_chars)


def make_provider(backend: str = "lexical", **kwargs) -> BaseRecallProvider:
    if backend == "lexical":
        return LexicalProvider()
    if backend == "vector":
        return VectorProvider(**kwargs)
    raise VectorUnavailableError("unknown recall backend %r (use lexical/vector)" % backend)
