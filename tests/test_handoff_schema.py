"""Production handoff schema form: units, archived exclusion, private context."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from memorix.retrieval.context import recent_private_context
from memorix.retrieval.store import load_rows
from memorix.schema import load_schema
from memorix.store import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "self-learning.schema.json"


def _db(tmp_path):
    path = tmp_path / "messages.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "create table memories (id integer primary key, group_id text not null, "
        "user_id text not null, content text not null, importance integer not null, "
        "memory_type text, created_at bigint not null, last_accessed bigint, access_count int, emotion text)"
    )
    conn.execute(
        "create table raw_messages (id integer primary key, sender_id text not null, "
        "sender_name text, message text not null, group_id text, timestamp bigint not null)"
    )
    conn.execute(
        "create table bot_messages (id integer primary key, group_id text not null, "
        "message text not null, timestamp bigint not null)"
    )
    conn.executemany(
        "insert into memories values (?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "g", "u", "石头门项目=破解打包", 8, "semantic", 1_792_512_135_055, 0, 0, None),
            (2, "g", "u", "归档旧事", 2, "archived", 1_792_512_000_000, 0, 0, None),
        ],
    )
    conn.executemany(
        "insert into raw_messages values (?,?,?,?,?,?)",
        [
            (1, "u", "尘风", "私聊原话一", "u", 1_792_512_471),
            (2, "u", "尘风", "私聊原话二", "u", 1_792_512_500),
            (3, "other", "群友", "群友的话", "g", 1_792_512_510),
        ],
    )
    conn.execute("insert into bot_messages values (1,'g','回复',1792512520)")
    conn.commit()
    conn.close()
    return path


def test_handoff_example_loads_metadata():
    schema = load_schema(EXAMPLE)
    assert schema.memories.table == "memories"
    assert schema.memories.unit == "ms"
    assert schema.raw_messages is not None and schema.raw_messages.unit == "s"
    assert schema.bot_messages is not None and schema.bot_messages.unit == "s"
    assert schema.exclude_types == ("archived",)
    assert schema.private_chat_by_group_equals_sender is True


def test_handoff_schema_reads_and_excludes_archived(tmp_path):
    db = _db(tmp_path)
    with SQLiteStore(db, readonly=True, schema=EXAMPLE) as store:
        assert len(store.iter_memories()) == 2  # diagnoses count archived too
        assert store.max_message_ids() == (3, 1)
    rows = load_rows(db, schema=EXAMPLE)
    assert [row.id for row in rows] == [1]  # archived excluded from recall


def test_private_context_excludes_group_members(tmp_path):
    db = _db(tmp_path)
    text = recent_private_context(db, "u", limit=4, schema=EXAMPLE)
    assert "私聊原话" in text
    assert "群友的话" not in text


def test_handoff_inline_json_also_works(tmp_path):
    db = _db(tmp_path)
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    with SQLiteStore(db, readonly=True, schema=data) as store:
        assert len(store.iter_memories()) == 2
