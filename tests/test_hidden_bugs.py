"""Regression tests for audited hidden bugs (paths, limits, clocks, metrics)."""
from __future__ import annotations

import sqlite3

from memorix.observability import MetricEvent, MetricsCollector
from memorix.retrieval.score import recall
from memorix.retrieval.store import load_rows
from memorix.store import SQLiteStore, backup_database, readonly_uri


def make_db(path, rows=(("auto_patrol", "石头门"),)):
    conn = sqlite3.connect(path)
    conn.execute("create table memories (id integer primary key, memory_type text, importance integer, created_at integer, content text, group_id text, user_id text)")
    conn.execute("create table raw_messages (id integer primary key, timestamp integer, message text)")
    conn.execute("create table bot_messages (id integer primary key, timestamp integer, message text)")
    for index, (memory_type, content) in enumerate(rows, start=1):
        conn.execute(
            "insert into memories values (?,?,?,?,?,?,?)",
            (index, memory_type, 7, 1_800_000_000_000, content, "g", "u"),
        )
    conn.commit()
    conn.close()


def test_readonly_uri_encodes_question_mark(tmp_path):
    db = tmp_path / "weird?name#x.db"
    make_db(db)
    assert "%3F" in readonly_uri(db)
    with SQLiteStore(db, readonly=True) as store:
        store.require_schema()
        assert len(store.iter_memories()) == 1
    assert len(load_rows(db)) == 1
    backup = backup_database(db, tmp_path / "bk")
    with SQLiteStore(backup, readonly=True) as store:
        assert len(store.iter_memories()) == 1


def test_fetch_messages_non_positive_limit_is_empty(patrol_db):
    with SQLiteStore(patrol_db, readonly=True) as store:
        assert store.fetch_messages("raw_messages", 0, 0) == []
        assert store.fetch_messages("raw_messages", 0, -5) == []


def test_recall_metrics_top_k_is_effective_cap():
    from memorix.retrieval.bench import fixture_rows

    collector = MetricsCollector()
    recall(
        "这个项目最困难的阶段是什么",
        rows=fixture_rows(),
        context="这次我指定一个，石头门",
        top_k=2,
        metrics=collector,
    )
    assert collector.snapshot()["recall_top_k"] <= 2


def test_metrics_none_latency_not_counted():
    collector = MetricsCollector()
    collector.record(MetricEvent("judge", "sent"))
    assert "judge" not in collector.snapshot()["latency_ms"]


def test_parse_ts_extreme_values_do_not_raise():
    from memorix.policy.timeparse import parse_ts

    huge = parse_ts("999999999999999999999")
    assert isinstance(huge, int) and huge > 0  # finite numeric strings are accepted
    assert parse_ts(float("inf")) == 0
    assert parse_ts(float("nan")) == 0
    assert parse_ts(object()) == 0
