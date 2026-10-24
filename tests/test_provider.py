"""Pluggable recall providers: lexical default, vector with caller embedder."""
from __future__ import annotations

from memorix.retrieval.provider import (
    LexicalProvider,
    VectorProvider,
    VectorUnavailableError,
    make_provider,
)
from memorix.retrieval.score import recall
from memorix.retrieval.store import RetrievalRow
from memorix.retrieval.tokens import tokens


def embed(texts):
    """Deterministic debug embedder: hashed character bag (not semantic)."""
    out = []
    for text in texts:
        vector = [0.0] * 64
        for char in text:
            vector[hash(char) % 64] += 1.0
        out.append(vector)
    return out


def rows():
    return [
        RetrievalRow(1, "石头门项目=破解打包", "manual_remember", 9, 1, "g", "u", frozenset(tokens("石头门项目=破解打包"))),
        RetrievalRow(2, "今天天气不错", "auto_patrol", 5, 1, "g", "u", frozenset(tokens("今天天气不错"))),
        RetrievalRow(3, "别人的记忆", "auto_patrol", 5, 1, "g", "other", frozenset(tokens("别人的记忆"))),
    ]


def test_lexical_provider_matches_recall():
    query = "石头门"
    provider = LexicalProvider()
    from memorix.retrieval.score import recall as lexical
    assert provider.recall(query, rows=rows(), context="这次我指定一个石头门") == lexical(
        query, rows=rows(), context="这次我指定一个石头门"
    )


def test_vector_provider_returns_topical_row():
    provider = VectorProvider(embed)
    text = provider.recall("石头门", rows=rows(), user_id="u", top_k=2)
    assert "石头门" in text
    assert "今天天气" not in text


def test_vector_provider_filters_users_and_empty():
    provider = VectorProvider(embed)
    only_other = [row for row in rows() if row.user_id == "other"]
    assert provider.recall("别人的记忆", rows=only_other, user_id="u") == ""
    assert provider.recall("", rows=rows()) == ""


def test_vector_provider_caches_embeddings():
    calls = []

    def counting(texts):
        calls.append(list(texts))
        return embed(texts)

    provider = VectorProvider(counting)
    provider.recall("石头门", rows=rows(), top_k=1)
    first = len(calls)
    provider.recall("天气", rows=rows(), top_k=1)
    assert len(calls) == first + 1  # query embed only; rows cached
    assert any("石头门项目" in batch[0] for batch in calls)


def test_vector_provider_requires_embedder():
    try:
        VectorProvider(None)
    except VectorUnavailableError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected VectorUnavailableError")


def test_make_provider():
    assert make_provider("lexical").name == "lexical"
    assert make_provider("vector", embedder=embed).name == "vector"
    try:
        make_provider("nope")
    except VectorUnavailableError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected VectorUnavailableError")
