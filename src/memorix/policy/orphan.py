"""Orphan-batch gate (report-only).

An "orphan" is a patrol-written memory whose ``created_at`` is later than the
last successful ``finish``: the cursor never advanced past it. Production only
reports these (other components also write these memory types), so this kernel
must not turn the gate into a hard block.
"""
from __future__ import annotations

from typing import Any, Iterable

from ..models import OrphanRecord, field_of
from .timeparse import parse_ts

__all__ = ["ORPHAN_MEMORY_TYPES", "detect_orphans"]

# Types the patrol itself writes into. ``profile`` was added 2026-10-17; the
# other components can also write several of these, hence report-only.
ORPHAN_MEMORY_TYPES: tuple[str, ...] = (
    "auto_patrol",
    "episodic",
    "contract",
    "learning_gap",
    "profile",
    "intent",
)


def detect_orphans(
    memories: Iterable[Any],
    last_finish_ts: Any,
    orphan_types: Iterable[str] = ORPHAN_MEMORY_TYPES,
) -> list[OrphanRecord]:
    """Return memories written after ``last_finish_ts``, sorted by id.

    ``<=`` boundary means "not an orphan" (the cursor did cover it), matching
    the production gate. With no finish record the answer is always empty.
    """
    finish_ts = int(last_finish_ts or 0)
    if not finish_ts:
        return []
    wanted = frozenset(orphan_types)
    orphans: list[OrphanRecord] = []
    for row in memories:
        memory_type = str(field_of(row, "memory_type") or "")
        if memory_type not in wanted:
            continue
        created_at = parse_ts(field_of(row, "created_at"))
        if created_at > finish_ts:
            orphans.append(
                OrphanRecord(
                    memory_id=int(field_of(row, "id") or 0),
                    memory_type=memory_type,
                    importance=field_of(row, "importance", 0),
                    created_at=created_at,
                )
            )
    orphans.sort(key=lambda item: item.memory_id)
    return orphans
