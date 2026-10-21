"""Decay planner: PATROL_SOP.md §5 decay rules (there is no production code)."""
from __future__ import annotations

from memorix.policy.decay import plan_decay

NOW = 1_800_000_000
DAY = 86_400


def mem(memory_id, memory_type="auto_patrol", importance=3, age_days=31):
    return {
        "id": memory_id,
        "memory_type": memory_type,
        "importance": importance,
        "created_at": NOW - age_days * DAY,
    }


def test_stale_low_importance_decays_by_one():
    actions = plan_decay([mem(1, importance=3, age_days=31)], NOW)
    assert len(actions) == 1
    action = actions[0]
    assert (action.memory_id, action.old_importance, action.new_importance) == (1, 3, 2)
    assert action.new_type == "auto_patrol"


def test_decay_to_zero_archives():
    actions = plan_decay([mem(1, importance=1, age_days=31)], NOW)
    assert actions[0].new_importance == 0
    assert actions[0].new_type == "archived"


def test_fresh_memory_is_not_decayed():
    assert plan_decay([mem(1, importance=3, age_days=29)], NOW) == []


def test_thirty_day_boundary_is_strictly_greater():
    assert plan_decay([mem(1, importance=3, age_days=30)], NOW) == []


def test_importance_above_three_is_not_decayed():
    assert plan_decay([mem(1, importance=4, age_days=31)], NOW) == []


def test_contract_never_decays():
    assert plan_decay([mem(1, memory_type="contract", importance=3, age_days=999)], NOW) == []


def test_importance_seven_plus_is_exempt():
    assert plan_decay([mem(1, importance=7, age_days=999)], NOW) == []
    assert plan_decay([mem(1, importance=8, age_days=999)], NOW) == []


def test_already_archived_is_skipped():
    assert plan_decay([mem(1, memory_type="archived", importance=2, age_days=999)], NOW) == []


def test_unparseable_created_at_is_skipped():
    rows = [{"id": 1, "memory_type": "auto_patrol", "importance": 3, "created_at": "n/a"}]
    assert plan_decay(rows, NOW) == []
    rows = [{"id": 1, "memory_type": "auto_patrol", "importance": 3, "created_at": 0}]
    assert plan_decay(rows, NOW) == []


def test_text_importance_is_skipped_not_guessed():
    rows = [{"id": 1, "memory_type": "auto_patrol", "importance": "system", "created_at": NOW - 999 * DAY}]
    assert plan_decay(rows, NOW) == []


def test_custom_age_threshold_and_sorted_output():
    rows = [mem(9, importance=2, age_days=2), mem(3, importance=2, age_days=2), mem(5, importance=2)]
    actions = plan_decay(rows, NOW, min_age_days=1)
    assert [action.memory_id for action in actions] == [3, 5, 9]


def test_all_actions_carry_a_reason():
    actions = plan_decay([mem(1, importance=3, age_days=31)], NOW)
    assert actions[0].reason == "stale>30d"
