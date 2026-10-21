"""Storage adapter + cursor state: read-only default, transactional writes, backups."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3

import pytest

from memorix.models import DecayAction, IntentUpdate, Promotion
from memorix.state import (
    PatrolState,
    StateError,
    advance_after_finish,
    decide_status,
    initial_state,
    load_state,
    save_state,
)
from memorix.store import (
    ReadOnlyStoreError,
    SchemaError,
    SQLiteStore,
    StoreError,
    backup_database,
    copy_file_backup,
)

NOW = 1_800_000_000


# ── store ────────────────────────────────────────────────────────────
def test_require_schema_success(patrol_db):
    with SQLiteStore(patrol_db, readonly=True) as store:
        store.require_schema()


def test_require_schema_missing_tables(tmp_path):
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    with pytest.raises(SchemaError):
        with SQLiteStore(empty, readonly=True) as store:
            store.require_schema()


def test_missing_database_is_an_error(tmp_path):
    with pytest.raises(StoreError):
        SQLiteStore(tmp_path / "nope.db")


def test_reads(patrol_db):
    with SQLiteStore(patrol_db, readonly=True) as store:
        memories = store.iter_memories()
        assert len(memories) == 8
        assert [m.id for m in store.iter_memories(["episodic"])] == [3, 4, 6]
        assert store.get_memory(5).memory_type == "contract"
        assert store.get_memory(999) is None
        assert store.memories_by_id([1, 8]).keys() == {1, 8}
        assert store.count_by_type()["episodic"] == 3
        assert store.max_message_ids() == (4, 2)
        rows = store.fetch_messages("raw_messages", 1, 2)
        assert [row["id"] for row in rows] == [2, 3]
        with pytest.raises(StoreError):
            store.fetch_messages("memories", 0, 1)
        names = {row["sender_id"]: row["sender_name"] for row in store.sender_name_rows()}
        assert names == {"owner": "尘风", "noodle": "牛杂"}


def test_readonly_store_refuses_writes(patrol_db):
    with SQLiteStore(patrol_db, readonly=True) as store:
        with pytest.raises(ReadOnlyStoreError):
            store.apply_decay_actions([DecayAction(6, "episodic", 2, 1, "episodic")])


def test_writable_store_applies_updates_transactionally(patrol_db):
    with SQLiteStore(patrol_db, readonly=False) as store:
        changed = store.apply_decay_actions([DecayAction(6, "episodic", 2, 1, "episodic")])
        assert changed == 1
    with SQLiteStore(patrol_db, readonly=True) as store:
        assert store.get_memory(6).importance == 1


def test_bad_update_rolls_back_whole_transaction(patrol_db):
    with SQLiteStore(patrol_db, readonly=False) as store:
        with pytest.raises(StoreError):
            store.apply_decay_actions(
                [
                    DecayAction(6, "episodic", 2, 1, "episodic"),
                    DecayAction(999, "episodic", 2, 1, "episodic"),
                ]
            )
    with SQLiteStore(patrol_db, readonly=True) as store:
        assert store.get_memory(6).importance == 2  # rolled back


def test_apply_intents_and_promotions(patrol_db):
    with SQLiteStore(patrol_db, readonly=False) as store:
        store.apply_intent_updates(
            [IntentUpdate(8, "episodic", 6, "[意图已过期,2026-01-01] x")]
        )
        store.apply_promotions([Promotion(3, "t", "episodic", "auto_patrol", 6, 7)])
    with SQLiteStore(patrol_db, readonly=True) as store:
        assert store.get_memory(8).memory_type == "episodic"
        assert store.get_memory(8).importance == 6
        assert store.get_memory(3).memory_type == "auto_patrol"
        assert store.get_memory(3).importance == 7


def test_backup_to_creates_consistent_copy(patrol_db, tmp_path):
    destination = tmp_path / "backup.db"
    with SQLiteStore(patrol_db, readonly=True) as store:
        store.backup_to(destination)
    with SQLiteStore(destination, readonly=True) as copy:
        assert len(copy.iter_memories()) == 8


def test_backup_database_and_file_backup(patrol_db, tmp_path, state_file):
    backup = backup_database(patrol_db, tmp_path / "bk", tag="test")
    assert backup.exists()
    with SQLiteStore(backup, readonly=True) as store:
        assert len(store.iter_memories()) == 8
    state_file.write_text('{"last_run_ts": 1}', encoding="utf-8")
    copied = copy_file_backup(state_file, tmp_path / "bk", tag="test")
    assert copied is not None and copied.exists()
    assert copy_file_backup(tmp_path / "missing.json", tmp_path / "bk") is None


# ── state ────────────────────────────────────────────────────────────
def test_load_state_missing_and_corrupt(tmp_path):
    assert load_state(tmp_path / "none.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{bad", encoding="utf-8")
    with pytest.raises(StateError):
        load_state(broken)
    wrong = tmp_path / "wrong.json"
    wrong.write_text("[]", encoding="utf-8")
    with pytest.raises(StateError):
        load_state(wrong)


def test_state_roundtrip_and_atomic_write(tmp_path):
    path = tmp_path / "state.json"
    state = PatrolState(
        last_run_ts=NOW,
        last_user_msg_id=4,
        last_bot_msg_id=2,
        backfill=True,
        last_finish_ts=NOW - 10,
        pending_user_end=4,
        pending_bot_end=2,
    )
    save_state(path, state)
    assert load_state(path) == state
    assert not (tmp_path / "state.json.tmp").exists()


def test_save_state_takes_a_backup(tmp_path, state_file):
    save_state(state_file, PatrolState(last_run_ts=1))
    save_state(state_file, PatrolState(last_run_ts=2), backup_dir=tmp_path / "bk")
    backups = list((tmp_path / "bk").glob("last_patrol.json-preapply-*"))
    assert len(backups) == 1


def test_state_from_mapping_tolerates_bad_numbers():
    state = PatrolState.from_mapping({"last_run_ts": "oops", "last_finish_ts": None})
    assert state.last_run_ts == 0 and state.last_finish_ts == 0


def test_decide_status_first_run():
    decision = decide_status(None, user_max=10, bot_max=5, new_user_count=0, now=NOW)
    assert decision.status == "FIRST"


def test_decide_status_cooldown():
    state = PatrolState(last_run_ts=NOW - 100)
    decision = decide_status(state, user_max=10, bot_max=5, new_user_count=99, now=NOW)
    assert decision.status == "SKIP" and "冷却" in decision.reason


def test_decide_status_too_few_messages():
    state = PatrolState(last_run_ts=NOW - 7 * 3600)
    decision = decide_status(state, user_max=10, bot_max=5, new_user_count=3, now=NOW)
    assert decision.status == "SKIP" and "消息太少" in decision.reason


def test_decide_status_work():
    state = PatrolState(last_run_ts=NOW - 7 * 3600)
    decision = decide_status(state, user_max=10, bot_max=5, new_user_count=10, now=NOW)
    assert decision.status == "WORK" and not decision.backlog


def test_decide_status_backfill_forces_work():
    state = PatrolState(last_run_ts=NOW, backfill=True)
    decision = decide_status(state, user_max=10, bot_max=5, new_user_count=0, now=NOW)
    assert decision.status == "WORK" and decision.backlog


def test_decide_status_backlog_over_batch_limit():
    state = PatrolState(last_run_ts=NOW, last_user_msg_id=0)
    decision = decide_status(state, user_max=100, bot_max=5, new_user_count=0, now=NOW)
    assert decision.status == "WORK" and decision.backlog


def test_advance_after_finish_normal_and_backfill():
    state = PatrolState(last_run_ts=NOW - 999, last_user_msg_id=1, last_bot_msg_id=1)
    normal = advance_after_finish(state, user_end=10, bot_end=8, user_max=10, now=NOW)
    assert (normal.last_user_msg_id, normal.last_run_ts) == (10, NOW)
    assert normal.backfill is False
    backlog = advance_after_finish(state, user_end=10, bot_end=8, user_max=20, now=NOW)
    assert backlog.backfill is True
    assert backlog.last_run_ts == state.last_run_ts


def test_initial_state_sets_cursor_to_current():
    state = initial_state(42, 24, NOW)
    assert (state.last_user_msg_id, state.last_bot_msg_id, state.last_run_ts) == (42, 24, NOW)


def test_backups_in_same_second_do_not_collide(patrol_db, tmp_path):
    first = backup_database(patrol_db, tmp_path / "bk", tag="same")
    second = backup_database(patrol_db, tmp_path / "bk", tag="same")
    assert first != second and first.exists() and second.exists()
