"""Port of the orphan-gate checks (production tests/test_orphan_gate.py 1-6)."""
from __future__ import annotations

from memorix.policy.orphan import ORPHAN_MEMORY_TYPES, detect_orphans

NOW = 1_800_000_000


def mem(memory_id, memory_type, importance, created_at):
    return {
        "id": memory_id,
        "memory_type": memory_type,
        "importance": importance,
        "created_at": created_at,
    }


def ids(orphans):
    return [orphan.memory_id for orphan in orphans]


def test_clean_batch_has_no_orphans():
    rows = [mem(1, "learning_gap", 8, NOW - 9000), mem(2, "episodic", 7, NOW - 8000)]
    assert detect_orphans(rows, NOW - 5000) == []


def test_memory_after_last_finish_is_orphan():
    rows = [mem(1, "learning_gap", 8, NOW - 9000), mem(2, "learning_gap", 8, NOW - 100)]
    orphans = detect_orphans(rows, NOW - 5000)
    assert ids(orphans) == [2]
    assert orphans[0].memory_type == "learning_gap"
    assert orphans[0].created_at == NOW - 100


def test_created_at_equal_to_finish_is_not_orphan():
    rows = [mem(1, "auto_patrol", 7, NOW - 5000)]
    assert detect_orphans(rows, NOW - 5000) == []


def test_only_watched_types_are_reported():
    rows = [
        mem(1, "auto_patrol", 7, NOW),
        mem(2, "profile", 9, NOW),
        mem(3, "archived", 5, NOW),
        mem(4, "user_preference", 9, NOW),
    ]
    orphans = detect_orphans(rows, NOW - 5000)
    assert ids(orphans) == [1, 2]
    assert 3 not in ids(orphans) and 4 not in ids(orphans)


def test_other_writers_can_inflate_candidates_by_design():
    rows = [mem(i, "auto_patrol", 7, NOW - i) for i in range(1, 6)]
    orphans = detect_orphans(rows, NOW - 100)
    assert len(orphans) >= 1


def test_no_finish_record_means_no_orphans():
    assert detect_orphans([mem(1, "learning_gap", 8, NOW)], {}) == []
    assert detect_orphans([mem(1, "learning_gap", 8, NOW)], 0) == []


def test_mixed_timestamp_encodings_are_normalised():
    # ms, seconds and ISO text all live in the same production column.
    rows = [
        mem(1, "auto_patrol", 7, NOW * 1000),  # milliseconds
        mem(2, "auto_patrol", 7, NOW),  # seconds
        mem(3, "auto_patrol", 7, "2026-01-01T00:00:00"),  # ISO (older than finish)
    ]
    orphans = detect_orphans(rows, NOW - 5000)
    assert ids(orphans) == [1, 2]


def test_output_is_sorted_by_id_even_for_unsorted_input():
    rows = [
        mem(5, "auto_patrol", 7, NOW),
        mem(2, "auto_patrol", 7, NOW),
        mem(9, "auto_patrol", 7, NOW),
    ]
    assert ids(detect_orphans(rows, NOW - 5000)) == [2, 5, 9]


def test_custom_orphan_types():
    rows = [mem(1, "auto_patrol", 7, NOW), mem(2, "episodic", 7, NOW)]
    assert ids(detect_orphans(rows, NOW - 5000, ["episodic"])) == [2]


def test_default_types_match_production_set():
    assert ORPHAN_MEMORY_TYPES == (
        "auto_patrol",
        "episodic",
        "contract",
        "learning_gap",
        "profile",
        "intent",
    )
