"""Episodic -> semantic consolidation (memory consolidation step 5, promotion half).

There is **no consolidation code in production** — only PATROL_SOP.md §5 prose:
"look at the 5 most recent episodic memories; if a theme/project/person repeats
in >= 2 of them, promote the most condensed, information-complete one:
memory_type episodic -> auto_patrol, importance += 1 (cap 9)."

"Most condensed / most complete" is a semantic judgement. This kernel therefore
keeps only the deterministic parts (window, grouping, selection, promotion
arithmetic) and requires the caller to inject:

* ``theme_key(row) -> hashable`` — semantic theme/project/person key;
* ``rank_key(row) -> comparable`` — semantic quality score.

In production those two callables are provided by the LLM/adapter step. M0 does
not invent a keyword heuristic, so semantic quality is out of scope until M2/M3.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from ..models import Promotion, as_int, field_of

__all__ = [
    "RECENT_EPISODIC_WINDOW",
    "recent_episodic",
    "plan_consolidation",
    "validate_plan",
]

RECENT_EPISODIC_WINDOW = 5


def recent_episodic(memories: Iterable[Any], window: int = RECENT_EPISODIC_WINDOW) -> list[Any]:
    """The ``window`` most recent episodic rows, newest id first."""
    episodic = [
        row
        for row in memories
        if str(field_of(row, "memory_type") or "") == "episodic"
    ]
    episodic.sort(key=lambda row: as_int(field_of(row, "id")), reverse=True)
    return episodic[: max(0, int(window))]


def plan_consolidation(
    memories: Iterable[Any],
    *,
    theme_key: Callable[[Any], Any],
    rank_key: Callable[[Any], Any],
    window: int = RECENT_EPISODIC_WINDOW,
    min_occurrences: int = 2,
    max_importance: int = 9,
) -> list[Promotion]:
    """Plan episodic->auto_patrol promotions for repeated themes.

    Within one theme the best ``rank_key`` row is chosen (ties: lower id first,
    for determinism). Only rows that are currently ``episodic`` can be promoted.
    """
    if not callable(theme_key) or not callable(rank_key):
        raise TypeError("theme_key and rank_key must be callables (semantic injection points)")

    window_rows = recent_episodic(memories, window=window)
    groups: dict[Any, list[Any]] = {}
    for row in window_rows:
        theme = theme_key(row)
        if theme is None or theme == "":
            continue
        groups.setdefault(theme, []).append(row)

    promotions: list[Promotion] = []
    for theme, rows in groups.items():
        if len(rows) < int(min_occurrences):
            continue
        best = rows[0]
        best_score = rank_key(best)
        for row in rows[1:]:
            score = rank_key(row)
            if score > best_score or (
                score == best_score
                and as_int(field_of(row, "id")) < as_int(field_of(best, "id"))
            ):
                best, best_score = row, score

        if str(field_of(best, "memory_type") or "") != "episodic":
            continue
        old_importance = as_int(field_of(best, "importance"), 0)
        new_importance = min(int(max_importance), old_importance + 1)
        promotions.append(
            Promotion(
                memory_id=as_int(field_of(best, "id")),
                theme=str(theme),
                old_type="episodic",
                new_type="auto_patrol",
                old_importance=old_importance,
                new_importance=new_importance,
                rank=best_score,
            )
        )

    promotions.sort(key=lambda promotion: promotion.memory_id)
    return promotions


def validate_plan(
    memories,
    plan,
    *,
    window: int = RECENT_EPISODIC_WINDOW,
    max_importance: int = 9,
):
    """Validate an externally produced promotion plan (LLM/adapter) — no guessing.

    Returns ``(promotions, errors)``. A plan item is only accepted when its
    ``memory_id`` is inside the deterministic recent-episodic window and still
    typed ``episodic``; importance arithmetic is recomputed here, never trusted
    from the input.
    """
    window_rows = recent_episodic(memories, window)
    by_id = {as_int(field_of(row, "id")): row for row in window_rows}
    if not isinstance(plan, list):
        return [], ["plan must be a JSON list"]

    promotions = []
    errors = []
    seen = set()
    for index, item in enumerate(plan):
        if not isinstance(item, dict):
            errors.append("item %d is not an object" % index)
            continue
        try:
            memory_id = int(item.get("memory_id"))
        except (TypeError, ValueError):
            errors.append("item %d: invalid memory_id %r" % (index, item.get("memory_id")))
            continue
        theme = str(item.get("theme") or "").strip()
        if not theme:
            errors.append("#%d: theme is required" % memory_id)
            continue
        row = by_id.get(memory_id)
        if row is None:
            errors.append("#%d: not in the most recent %d episodic window" % (memory_id, window))
            continue
        if memory_id in seen:
            errors.append("#%d: duplicate plan entry" % memory_id)
            continue
        seen.add(memory_id)
        old_importance = as_int(field_of(row, "importance"), 0)
        promotions.append(
            Promotion(
                memory_id=memory_id,
                theme=theme,
                old_type="episodic",
                new_type="auto_patrol",
                old_importance=old_importance,
                new_importance=min(int(max_importance), old_importance + 1),
                rank=item.get("rank"),
            )
        )
    promotions.sort(key=lambda promotion: promotion.memory_id)
    return promotions, errors
