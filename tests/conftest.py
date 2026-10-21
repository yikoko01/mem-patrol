"""Make ``src/`` importable even when pytest is invoked without the ini file."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ── M1 fixtures: a production-shaped SQLite database in tmp_path ─────
import sqlite3

import pytest

NOW = 1_800_000_000
DAY = 86_400

SCHEMA = """
create table memories (
    id integer primary key,
    memory_type text,
    importance integer,
    created_at integer,
    content text,
    group_id text,
    user_id text
);
create table raw_messages (
    id integer primary key,
    timestamp integer,
    message text,
    sender_id text,
    sender_name text,
    group_id text
);
create table bot_messages (
    id integer primary key,
    timestamp integer,
    message text
);
"""

DEFAULT_MEMORIES = [
    (1, "auto_patrol", 7, NOW * 1000, "语义记忆", "g", "u"),
    (2, "learning_gap", 8, (NOW - 30) * 1000, "教训", "g", "u"),
    (3, "episodic", 6, (NOW - 31 * DAY) * 1000, "情景 A", "g", "u"),
    (4, "episodic", 5, (NOW - 32 * DAY) * 1000, "情景 B", "g", "u"),
    (5, "contract", 9, (NOW - 999 * DAY) * 1000, "契约", "g", "u"),
    (6, "episodic", 2, (NOW - 31 * DAY) * 1000, "老情景", "g", "u"),
    (7, "archived", 0, (NOW - 999 * DAY) * 1000, "归档", "g", "u"),
    (8, "intent", 8, (NOW - 1) * 1000, "【意图·有效期至 2026-01-01】做 A", "g", "u"),
]

DEFAULT_RAW = [
    (1, NOW - 400, "旧消息", "owner", "尘风", "g"),
    (2, NOW - 300, "群友消息", "noodle", "牛杂", "g"),
    (3, NOW - 200, "私有消息", "owner", "", "owner"),
    (4, NOW - 100, "最新", "owner", "尘风", "g"),
]

DEFAULT_BOT = [
    (1, NOW - 350, "好的",),
    (2, NOW - 150, "收到",),
]


def _build(path: Path, memories, raw, bot) -> Path:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("insert into memories values (?,?,?,?,?,?,?)", memories)
        conn.executemany(
            "insert into raw_messages (id,timestamp,message,sender_id,sender_name,group_id)"
            " values (?,?,?,?,?,?)",
            raw,
        )
        conn.executemany(
            "insert into bot_messages (id,timestamp,message) values (?,?,?)", bot
        )
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def make_patrol_db(tmp_path):
    """Factory: create a patrol-shaped DB with overridable rows."""

    def _make(name="messages.db", *, memories=None, raw=None, bot=None) -> Path:
        return _build(
            tmp_path / name,
            DEFAULT_MEMORIES if memories is None else memories,
            DEFAULT_RAW if raw is None else raw,
            DEFAULT_BOT if bot is None else bot,
        )

    return _make


@pytest.fixture
def patrol_db(make_patrol_db) -> Path:
    return make_patrol_db()


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "last_patrol.json"


@pytest.fixture
def ledger_file(tmp_path):
    return tmp_path / "change_history.md"


@pytest.fixture
def snapshot_file(tmp_path):
    return tmp_path / "audit_snapshot.json"


@pytest.fixture
def config_dir(tmp_path):
    directory = tmp_path / "config"
    directory.mkdir()
    (directory / "a.json").write_text('{"a": 1}', encoding="utf-8")
    (directory / "b.json").write_text('{"b": 2}', encoding="utf-8")
    return directory


@pytest.fixture
def write_state(state_file):
    import json

    def _write(**overrides):
        data = {
            "last_run_ts": NOW - 100,
            "last_user_msg_id": 2,
            "last_bot_msg_id": 1,
            "backfill": False,
            "last_finish_ts": NOW - 1000,
            "pending_user_end": None,
            "pending_bot_end": None,
        }
        data.update(overrides)
        state_file.write_text(json.dumps(data), encoding="utf-8")
        return state_file

    return _write


@pytest.fixture
def write_ledger(ledger_file):
    def _write(text="### 2026-10-20 23:00 · 自动巡检\n正文\n"):
        ledger_file.write_text(text, encoding="utf-8")
        return ledger_file

    return _write
