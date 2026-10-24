"""End-to-end integration on foreign SQLite schemas (read-only).

Covers SQLAlchemy-style tables, custom names, auto-detection, memory-only DBs,
private/group message separation and the CLI/MCP/doctor surfaces together.
"""
from __future__ import annotations

import json
import sqlite3

from memorix.diagnose import build_diagnosis
from memorix.mcp.server import Server
from memorix.retrieval.context import recent_private_context
from memorix.retrieval.store import load_rows
from memorix.store import SQLiteStore

USER = "u"


def _db(tmp_path, *, messages=True, table="long_term_memory"):
    path = tmp_path / "foreign.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "create table %s (id integer not null primary key, body varchar(255) not null, "
        "kind varchar(50), weight integer, created integer, group_id varchar(255), user_id varchar(255))" % table
    )
    conn.executemany(
        "insert into %s values (?,?,?,?,?,?,?)" % table,
        [
            (1, "项目最困难的阶段是盲改期", "semantic", 8, 1_792_000_000_000, "g", USER),
            (2, "归档旧事", "archived", 2, 1_792_000_001_000, "g", USER),
        ],
    )
    if messages:
        conn.execute("create table chat_messages (id integer primary key, timestamp integer, text text, sender_id text, sender_name text, group_id text)")
        conn.execute("create table bot_replies (id integer primary key, timestamp integer, text text)")
        conn.executemany(
            "insert into chat_messages values (?,?,?,?,?,?)",
            [
                (1, 1_792_000_010, "这次我指定一个，项目", USER, "user", USER),
                (2, 1_792_000_020, "群友的话", "other", "other", "g"),
            ],
        )
        conn.execute("insert into bot_replies values (?,?,?)", (1, 1_792_000_030, "回复"))
    conn.commit()
    conn.close()
    return path


def test_auto_detects_sqlalchemy_style_tables(tmp_path):
    db = _db(tmp_path)
    with SQLiteStore(db, readonly=True, schema="auto") as store:
        assert store.schema.memories.table == "long_term_memory"
        assert len(store.iter_memories()) == 2
        assert store.max_message_ids() == (2, 1)
    rows = load_rows(db, schema="auto")
    assert [row.id for row in rows] == [1]  # archived excluded
    private = recent_private_context(db, USER, schema="auto")
    assert "这次我指定一个" in private
    assert "群友" not in private


def test_explicit_mapping_memory_only_and_cli(tmp_path, capsys):
    db = _db(tmp_path, messages=False)
    mapping = {"memories": {"table": "long_term_memory", "id": "id", "content": "body",
                            "type": "kind", "importance": "weight", "created_at": "created"}}
    with SQLiteStore(db, readonly=True, schema=mapping) as store:
        assert len(store.iter_memories()) == 2
    from memorix.cli import main
    assert main(["diagnose", "--db", str(db), "--schema", json.dumps(mapping), "--now", "1792000010"]) == 0
    assert "MEMORIX_DIAGNOSIS" in capsys.readouterr().out
    assert main(["recall", "--db", str(db), "--schema", json.dumps(mapping), "--query", "最困难的阶段", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert 1 in data["memory_ids"]
    # message-dependent feature must fail clearly, not silently read wrong table
    assert main(["status", "--db", str(db), "--schema", json.dumps(mapping)]) == 4


def test_doctor_and_mcp_auto_on_foreign(tmp_path, capsys):
    db = _db(tmp_path)
    from memorix.cli import main
    assert main(["doctor", "--db", str(db), "--schema", "auto", "--json"]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["ok"] is True and doctor["db"]["memories"] == 2
    server = Server(profile="both")
    call = lambda name, args: server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                             "params": {"name": name, "arguments": args}})
    diag = call("memorix_diagnose", {"db": str(db), "schema": "auto", "now": 1_792_000_100})
    assert diag["result"]["isError"] is False and "MEMORIX_DIAGNOSIS" in diag["result"]["content"][0]["text"]
    recall = call("memorix_recall", {"db": str(db), "schema": "auto", "query": "最困难的阶段", "user_id": USER})
    assert recall["result"]["isError"] is False and "盲改期" in recall["result"]["content"][0]["text"]


def test_diagnosis_on_foreign_rows(tmp_path):
    db = _db(tmp_path)
    rows = load_rows(db, schema="auto")
    diagnosis = build_diagnosis(rows, now=1_792_000_100)
    assert diagnosis.total == 1
    assert diagnosis.distribution.get("semantic") == 1
