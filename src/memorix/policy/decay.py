"""Importance decay / archiving (memory consolidation step 5, decay half).

There is **no decay code in production** — only prose in PATROL_SOP.md §5:
"created_at older than 30 days and importance <= 3 -> importance -= 1; when it
reaches 0 change memory_type to 'archived'; hard exemptions: contract never
decays, importance >= 7 never decays."

This module implements that rule as a pure planner. It does not write anything;
an adapter (M1) applies the returned actions.
"""
from __future__ import annotations

from typing import Any, Iterable

from ..models import DecayAction, as_int, field_of
from .timeparse import parse_ts

__all__ = [
    "DECAY_MIN_AGE_DAYS",
    "DECAY_MAX_IMPORTANCE",
    "DECAY_FLOOR_IMPORTANCE",
    "DECAY_NEVER_TYPES",
    "DECAY_SKIP_TYPES",
    "plan_decay",
]

DECAY_MIN_AGE_DAYS = 30
DECAY_MAX_IMPORTANCE = 3
DECAY_FLOOR_IMPORTANCE = 7
# SOP hard exemption: contracts never decay.
DECAY_NEVER_TYPES: tuple[str, ...] = ("contract",)
# Already archived rows are skipped for idempotency (no negative importance).
DECAY_SKIP_TYPES: tuple[str, ...] = ("archived",)


def plan_decay(
    memories: Iterable[Any],
    now_ts: int,
    *,
    min_age_days: int = DECAY_MIN_AGE_DAYS,
    max_importance: int = DECAY_MAX_IMPORTANCE,
    floor_importance: int = DECAY_FLOOR_IMPORTANCE,
    never_types: Iterable[str] = DECAY_NEVER_TYPES,
    skip_types: Iterable[str] = DECAY_SKIP_TYPES,
) -> list[DecayAction]:
    """Plan one-step importance decays for stale low-importance memories.

    Notes on deliberately defensive choices (documented in docs/M0.md):
    * ``created_at`` that cannot be parsed (or is 0) is skipped, never treated as
      ancient, because the production table contains corrupt legacy rows;
    * non-integer ``importance`` (historical text values) is skipped;
    * ``importance <= 0`` is skipped (already at the floor).
    """
    frozen_never = frozenset(never_types)
    frozen_skip = frozenset(skip_types)
    min_age_seconds = int(min_age_days) * 86400
    actions: list[DecayAction] = []

    for row in memories:
        memory_type = str(field_of(row, "memory_type") or "")
        if memory_type in frozen_never or memory_type in frozen_skip:
            continue
        importance = as_int(field_of(row, "importance"), 0)
        if importance <= 0:
            continue
        # SOP explicit exemption (defensive: already covered by max_importance <= 3).
        if importance >= floor_importance or importance > max_importance:
            continue
        created_at = parse_ts(field_of(row, "created_at"))
        if created_at <= 0:
            continue
        if now_ts - created_at <= min_age_seconds:
            continue

        new_importance = importance - 1
        new_type = "archived" if new_importance == 0 else memory_type
        actions.append(
            DecayAction(
                memory_id=as_int(field_of(row, "id")),
                memory_type=memory_type,
                old_importance=importance,
                new_importance=new_importance,
                new_type=new_type,
                reason="stale>%dd" % min_age_days,
            )
        )

    actions.sort(key=lambda action: action.memory_id)
    return actions
