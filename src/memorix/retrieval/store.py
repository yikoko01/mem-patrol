"""Read-only memory reader for the recall scorer (M1.5)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..policy.timeparse import parse_ts
from ..store import SQLiteStore
from .tokens import single_line, tokens


@dataclass(frozen=True)
class RetrievalRow:
    id: int
    content: str
    memory_type: str
    importance: int
    created_at: int  # epoch seconds, normalised on load
    group_id: str
    user_id: str
    tokens: frozenset[str]


def load_rows(
    db_path: str | Path,
    *,
    as_of_ms: int | None = None,
    schema=None,
) -> list[RetrievalRow]:
    """Load non-archived memories read-only, optionally as of an epoch-ms cut.

    ``as_of_ms`` makes replay cases reproducible: a memory written after the
    historical question is excluded from that case's corpus.
    """
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError("database not found: %s" % path)
    with SQLiteStore(path, readonly=True, schema=schema) as store:
        store.require_schema()
        memories = store.iter_memories()
        excluded = set(store.schema.exclude_types)
    rows: list[RetrievalRow] = []
    for record in memories:
        memory_type = str(record.memory_type or "")
        if memory_type in excluded:
            continue
        content = single_line(record.content, 600)
        if not content:
            continue
        created_at = parse_ts(record.created_at)
        if as_of_ms is not None and created_at * 1000 > int(as_of_ms):
            continue
        rows.append(
            RetrievalRow(
                id=int(record.id),
                content=content,
                memory_type=memory_type,
                importance=int(record.importance or 0),
                created_at=created_at,
                group_id=str(record.group_id or ""),
                user_id=str(record.user_id or ""),
                tokens=frozenset(tokens(content)),
            )
        )
    return rows


def doc_freq(rows: list[RetrievalRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for token in row.tokens:
            counts[token] = counts.get(token, 0) + 1
    return counts
