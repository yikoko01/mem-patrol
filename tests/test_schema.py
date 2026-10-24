"""Foreign-schema support: explicit mapping, auto detection, memory-only DBs."""
from __future__ import annotations

import json
import sqlite3

import pytest

from memorix.diagnose import build_diagnosis
from memorix.retrieval.store import load_rows
from memorix.schema import SchemaError, load_schema, native_schema
from memorix.store import SQLiteStore
from memorix.mcp.server import Server


def _custom_db(tmp_path, *, messages: bool = False):
    path = tmp_path / "foreign.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "create table my_memories (id integer primary key, body text, kind text, "
        "weight integer, created_at integer, group_id text, user_id text)"
    )
    conn.execute(
        "insert into my_memories values (1,'石头门项目=破解打包','semantic',8,1800000000000,'g','u')"
    )
    if messages:
        conn.execute("create table chat_log (id integer primary key, ts integer, text text, role_id text, role_name text, group_id text)")
        conn.execute("create table reply_log (id integer primary key, ts integer, text text)")
        conn.execute("insert into chat_log values (1,1799999999,'在吗','u1','尘风','g')")
        conn.execute("insert into reply_log values (1,1800000000,'在')")
    conn.commit()
    conn.close()
    return path


def _mapping():
    return {
        "memories": {
            "table": "my_memories",
            "id": "id",
            "content": "body",
            "type": "kind",
            "importance": "weight",
            "created_at": "created_at",
            "group_id": "group_id",
            "user_id": "user_id",
        }
    }


def test_explicit_mapping_reads_foreign_memory_table(tmp_path):
    db = _custom_db(tmp_path)
    with SQLiteStore(db, readonly=True, schema=_mapping()) as store:
        store.require_schema()
        memories = store.iter_memories()
        assert len(memories) == 1
        assert memories[0].content.startswith("石头门")
        assert memories[0].memory_type == "semantic"
        assert memories[0].importance == 8
        assert store.get_memory(1).content == "石头门项目=破解打包"
        assert store.count_by_type() == {"semantic": 1}


def test_memory_only_schema_diagnose_and_recall(tmp_path):
    db = _custom_db(tmp_path)
    with SQLiteStore(db, readonly=True, schema=_mapping()) as store:
        with pytest.raises(SchemaError):
            store.max_message_ids()
    rows = load_rows(db, schema=_mapping())
    assert len(rows) == 1
    from memorix.retrieval.score import recall
    assert "石头门" in recall("石头门困难", rows=rows)
    diagnosis = build_diagnosis(load_rows(db, schema=_mapping()))
    assert diagnosis.total == 1 and diagnosis.findings


def test_auto_detect_foreign_tables(tmp_path):
    db = tmp_path / "auto.db"
    conn = sqlite3.connect(db)
    conn.execute("create table long_term_memory (id integer primary key, text text, kind text, weight int, created_at int)")
    conn.execute("insert into long_term_memory values (1,'项目笔记','note',5,1800000000000)")
    conn.execute("create table messages (id integer primary key, ts int, text text, role_id text, role_name text, group_id text)")
    conn.execute("create table assistant_messages (id integer primary key, ts int, text text)")
    conn.commit()
    conn.close()
    with SQLiteStore(db, readonly=True, schema="auto") as store:
        assert store.schema.name == "auto"
        assert store.schema.memories.table == "long_term_memory"
        assert len(store.iter_memories()) == 1
        assert store.max_message_ids() == (0, 0)


def test_auto_without_memories_table_errors(tmp_path):
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    with pytest.raises(SchemaError):
        SQLiteStore(db, schema="auto")


def test_missing_message_tables_have_clear_error(tmp_path):
    db = _custom_db(tmp_path)
    with SQLiteStore(db, readonly=True, schema=_mapping()) as store:
        with pytest.raises(SchemaError, match="message"):
            store.require_messages()
        with pytest.raises(SchemaError, match="raw_messages|message"):
            store.fetch_messages("raw_messages", 0, 10)


def test_custom_message_mapping(tmp_path):
    db = _custom_db(tmp_path, messages=True)
    mapping = {
        **_mapping(),
        "raw_messages": {
            "table": "chat_log",
            "id": "id",
            "timestamp": "ts",
            "message": "text",
            "sender_id": "role_id",
            "sender_name": "role_name",
            "group_id": "group_id",
        },
        "bot_messages": {"table": "reply_log", "id": "id", "timestamp": "ts", "message": "text"},
    }
    with SQLiteStore(db, readonly=True, schema=mapping) as store:
        assert store.max_message_ids() == (1, 1)
        rows = store.fetch_messages("raw_messages", 0, 5)
        assert rows[0]["sender_name"] == "尘风"
        assert rows[0]["message"] == "在吗"


def test_schema_identifier_validation():
    with pytest.raises(SchemaError):
        load_schema({"memories": {"table": "memories; drop table x"}})


def test_cli_and_mcp_with_schema_file(tmp_path, capsys):
    db = _custom_db(tmp_path)
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(_mapping()), encoding="utf-8")
    from memorix.cli import main
    assert main(["diagnose", "--db", str(db), "--schema", str(schema_file), "--now", "1800000000"]) == 0
    out = capsys.readouterr().out
    assert "MEMORIX_DIAGNOSIS" in out and "total=1" in out

    server = Server(profile="both")
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "memorix_recall",
                "arguments": {"db": str(db), "schema": str(schema_file), "query": "石头门"},
            },
        }
    )
    assert response["result"]["isError"] is False
    assert "石头门" in response["result"]["content"][0]["text"]


def test_cli_status_on_memory_only_errors_cleanly(tmp_path, capsys):
    db = _custom_db(tmp_path)
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(_mapping()), encoding="utf-8")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_run_ts": 1, "last_user_msg_id": 0}), encoding="utf-8")
    from memorix.cli import main
    code = main(["status", "--db", str(db), "--state", str(state), "--schema", str(schema_file)])
    assert code == 4
    assert "message" in capsys.readouterr().out


def test_partial_mapping_omitted_columns_are_null(tmp_path):
    db = tmp_path / "partial.db"
    conn = sqlite3.connect(db)
    conn.execute("create table t (id integer primary key, body text, created_at integer)")
    conn.execute("insert into t values (1,'只有正文',1800000000000)")
    conn.commit()
    conn.close()
    schema = {"memories": {"table": "t", "id": "id", "content": "body", "created_at": "created_at"}}
    with SQLiteStore(db, readonly=True, schema=schema) as store:
        memories = store.iter_memories()
        assert memories[0].memory_type == ""  # NULL, not the literal "memory_type"
        assert memories[0].importance == 0
        assert store.count_by_type() == {"memory": 1}


def test_write_without_importance_column_is_a_clear_schema_error(tmp_path):
    from memorix.models import DecayAction
    from memorix.store import SQLiteStore

    db = tmp_path / "partial.db"
    conn = sqlite3.connect(db)
    conn.execute("create table t (id integer primary key, body text, created_at integer)")
    conn.execute("insert into t values (1,'x',1)")
    conn.commit()
    conn.close()
    schema = {"memories": {"table": "t", "id": "id", "content": "body", "created_at": "created_at"}}
    with SQLiteStore(db, readonly=False, schema=schema) as store:
        with pytest.raises(SchemaError, match="importance"):
            store.apply_decay_actions([DecayAction(1, "semantic", 3, 2, "semantic")])
    conn = sqlite3.connect(db)
    assert conn.execute("select body from t where id=1").fetchone()[0] == "x"
    conn.close()


def test_mcp_orphan_accepts_schema(tmp_path):
    db = _custom_db(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"last_finish_ts": 1, "last_user_msg_id": 0}), encoding="utf-8")
    server = Server(profile="both")
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "memorix_orphan",
                "arguments": {"db": str(db), "schema": _mapping(), "state": str(state)},
            },
        }
    )
    assert response["result"]["isError"] is False
    assert "ORPHAN" in response["result"]["content"][0]["text"]


def test_auto_failure_suggests_closest_table_and_columns(tmp_path):
    db = tmp_path / "weird.db"
    conn = sqlite3.connect(db)
    conn.execute("create table weird_rows (pk integer primary key, body text, weight int)")
    conn.execute("insert into weird_rows values (1,'hello',5)")
    conn.commit()
    conn.close()
    with pytest.raises(SchemaError) as exc:
        SQLiteStore(db, schema="auto")
    message = str(exc.value)
    assert "weird_rows" in message and "body" in message
