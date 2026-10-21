"""Consolidation planner: deterministic window/group/select/arithmetic.

Semantic theme extraction and quality ranking are *injected* callables, so these
tests use explicit stubs. Production supplies them from the LLM/adapter.
"""
from __future__ import annotations

import pytest

from memorix.policy.consolidation import plan_consolidation, recent_episodic


def ep(memory_id, theme, importance=5, content=""):
    return {
        "id": memory_id,
        "memory_type": "episodic",
        "importance": importance,
        "content": content or f"content {memory_id}",
        "theme": theme,
    }


THEME = lambda row: row["theme"]  # noqa: E731 - tiny stub
RANK = lambda row: row["importance"]  # noqa: E731 - tiny stub


def test_repeated_theme_promotes_best_row():
    rows = [ep(1, "old"), ep(2, "proj", 5), ep(3, "misc"), ep(4, "proj", 7), ep(5, "misc2"), ep(6, "proj", 6)]
    promotions = plan_consolidation(rows, theme_key=THEME, rank_key=RANK)
    assert [promotion.memory_id for promotion in promotions] == [4]
    assert promotions[0].theme == "proj"
    assert promotions[0].old_type == "episodic"
    assert promotions[0].new_type == "auto_patrol"
    assert promotions[0].new_importance == 8


def test_window_is_the_five_most_recent_episodic():
    # id 1 is the 6th most recent -> outside the window; theme "old" repeats
    # only in id 1 and id 2, so after windowing there is nothing to promote.
    rows = [ep(1, "old"), ep(2, "old"), ep(3, "a"), ep(4, "b"), ep(5, "c"), ep(6, "d")]
    assert plan_consolidation(rows, theme_key=THEME, rank_key=RANK) == []


def test_single_occurrence_does_not_promote():
    rows = [ep(1, "x"), ep(2, "y"), ep(3, "z")]
    assert plan_consolidation(rows, theme_key=THEME, rank_key=RANK) == []


def test_importance_cap_is_nine():
    rows = [ep(1, "proj", 9), ep(2, "proj", 9)]
    promotions = plan_consolidation(rows, theme_key=THEME, rank_key=RANK)
    assert promotions[0].new_importance == 9


def test_rank_tie_breaks_on_lower_id():
    rows = [ep(1, "proj", 7), ep(2, "proj", 7)]
    promotions = plan_consolidation(rows, theme_key=THEME, rank_key=RANK)
    assert promotions[0].memory_id == 1


def test_only_episodic_rows_enter_the_window():
    rows = [
        {"id": 1, "memory_type": "auto_patrol", "importance": 9, "content": "x", "theme": "p"},
        {"id": 2, "memory_type": "auto_patrol", "importance": 9, "content": "y", "theme": "p"},
    ]
    assert plan_consolidation(rows, theme_key=THEME, rank_key=RANK) == []


def test_none_theme_is_skipped():
    rows = [ep(1, None), ep(2, None)]
    assert plan_consolidation(rows, theme_key=THEME, rank_key=RANK) == []


def test_theme_and_rank_callables_are_required():
    with pytest.raises(TypeError):
        plan_consolidation([], theme_key=None, rank_key=RANK)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        plan_consolidation([], theme_key=THEME, rank_key=None)  # type: ignore[arg-type]


def test_output_sorted_by_id():
    rows = [ep(2, "a"), ep(4, "a"), ep(1, "b"), ep(3, "b")]
    promotions = plan_consolidation(rows, theme_key=THEME, rank_key=RANK)
    assert [promotion.memory_id for promotion in promotions] == [1, 2]


def test_recent_episodic_newest_first():
    rows = [ep(1, "a"), ep(2, "a"), ep(3, "a")]
    assert [row["id"] for row in recent_episodic(rows, window=2)] == [3, 2]


def test_min_occurrences_can_be_raised():
    rows = [ep(1, "proj"), ep(2, "proj")]
    assert plan_consolidation(rows, theme_key=THEME, rank_key=RANK, min_occurrences=3) == []
