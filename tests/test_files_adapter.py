"""The only IO module in M0: fingerprints and snapshot persistence."""
from __future__ import annotations

import json

from memorix.adapters.files import (
    fingerprint_file,
    fingerprint_patterns,
    load_snapshot,
    save_snapshot,
)


def test_fingerprint_file(tmp_path):
    target = tmp_path / "a.json"
    target.write_text("hello", encoding="utf-8")
    state = fingerprint_file(str(target))
    assert state.path == str(target.resolve())
    assert len(state.md5) == 32
    assert state.mtime > 0


def test_fingerprint_patterns(tmp_path):
    (tmp_path / "a.json").write_text("a", encoding="utf-8")
    (tmp_path / "b.json").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    states = fingerprint_patterns([str(tmp_path / "*.json")])
    assert len(states) == 2
    assert all(state.path.endswith(".json") for state in states)


def test_load_snapshot_missing_or_corrupt(tmp_path):
    assert load_snapshot(str(tmp_path / "missing.json")) == {}
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert load_snapshot(str(broken)) == {}


def test_save_and_load_snapshot_roundtrip(tmp_path):
    path = tmp_path / "snap.json"
    snapshot = {"/tmp/a.json": "deadbeef"}
    save_snapshot(str(path), snapshot)
    assert load_snapshot(str(path)) == snapshot
    assert not (tmp_path / "snap.json.tmp").exists()
    assert json.loads(path.read_text(encoding="utf-8")) == snapshot
