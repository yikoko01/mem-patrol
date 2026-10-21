"""Privacy-preserving real-corpus regression: manifest + snapshot hash + ids."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from memorix.eval.real_corpus import check_corpus, normalized_sha256, sha256_file


def _db(tmp_path):
    path = tmp_path / "corpus.db"
    conn = sqlite3.connect(path)
    conn.execute("create table memories (id integer primary key, group_id text, user_id text, content text, importance int, memory_type text, created_at integer, last_accessed int, access_count int, emotion text)")
    conn.execute("create table raw_messages (id integer primary key, sender_id text, sender_name text, message text, group_id text, timestamp integer)")
    conn.execute("create table bot_messages (id integer primary key, group_id text, message text, timestamp integer)")
    content = "石头门项目=《命运石之门》破解打包"
    conn.execute("insert into memories values (1,'u','u',?,9,'manual_remember',1792510350000,0,0,null)", (content,))
    conn.execute("insert into raw_messages values (1,'u','u','石头门', 'u',1792510350)")
    conn.commit()
    conn.close()
    return path, content


def _manifest(path, content, *, expected_id=1, bad_hash=False):
    digest = normalized_sha256(content)
    if bad_hash:
        digest = "0" * 64
    return {
        "snapshot": {"sha256": sha256_file(path)},
        "queries": [
            {
                "id": "q1",
                "query": "石头门项目",
                "as_of_ts": 1792510350,
                "top_n": 3,
                "expected": [{"id": expected_id, "content_sha256": digest}],
            }
        ],
    }


def test_real_corpus_pass(tmp_path):
    db, content = _db(tmp_path)
    result = check_corpus(db, user_id="u", manifest=_manifest(db, content), schema="native")
    assert result["status"] == "PASS"
    assert result["queries"][0]["top_ids"][0] == 1


def test_real_corpus_fails_on_missing_expected_id(tmp_path):
    db, content = _db(tmp_path)
    result = check_corpus(db, user_id="u", manifest=_manifest(db, content, expected_id=999), schema="native")
    assert result["status"] == "FAIL"


def test_real_corpus_fails_on_content_hash(tmp_path):
    db, content = _db(tmp_path)
    result = check_corpus(db, user_id="u", manifest=_manifest(db, content, bad_hash=True), schema="native")
    assert result["status"] == "FAIL"


def test_real_corpus_fails_on_snapshot_hash(tmp_path):
    db, content = _db(tmp_path)
    manifest = _manifest(db, content)
    manifest["snapshot"]["sha256"] = "0" * 64
    result = check_corpus(db, user_id="u", manifest=manifest, schema="native")
    assert result["status"] == "FAIL"


def test_shipped_manifest_contains_no_raw_content():
    manifest = json.loads((__import__("pathlib").Path(__file__).resolve().parents[1] / "eval" / "real_corpus.json").read_text(encoding="utf-8"))
    raw = json.dumps(manifest, ensure_ascii=False)
    assert "石头门" not in raw and "命运石" not in raw
    assert len(manifest["queries"]) >= 2
    assert all("content" not in item for query in manifest["queries"] for item in query["expected"])
