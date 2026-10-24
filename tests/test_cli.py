"""M1 CLI: read-only by default, explicit --apply writes with backups."""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from memorix.cli import main
from memorix.state import load_state
from memorix.store import SQLiteStore

NOW = 1_800_000_000


def run(capsys, *argv):
    code = main([str(part) for part in argv])
    captured = capsys.readouterr()
    return code, captured.out


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_diagnose_text_and_strict(patrol_db, state_file, write_state, capsys):
    write_state()
    code, out = run(capsys, "diagnose", "--db", patrol_db, "--state", state_file, "--now", NOW)
    assert code == 0
    assert "MEMORIX_DIAGNOSIS" in out
    assert "total=8" in out
    assert "orphan=3" in out
    assert "decay_pending=1" in out
    code, _ = run(
        capsys, "diagnose", "--db", patrol_db, "--state", state_file, "--now", NOW, "--strict"
    )
    assert code == 1  # orphan-batch is HIGH


def test_diagnose_json(patrol_db, state_file, write_state, capsys):
    write_state()
    code, out = run(
        capsys, "diagnose", "--db", patrol_db, "--state", state_file, "--now", NOW, "--json"
    )
    assert code == 0
    data = json.loads(out)
    assert data["total"] == 8
    assert "distribution" in data


def test_diagnose_two_different_db_paths(make_patrol_db, capsys):
    first = make_patrol_db("one.db")
    second = make_patrol_db(
        "two.db",
        memories=[(1, "auto_patrol", 7, NOW * 1000, "only", "g", "u")],
        raw=[],
        bot=[],
    )
    code_one, out_one = run(capsys, "diagnose", "--db", first, "--now", NOW)
    code_two, out_two = run(capsys, "diagnose", "--db", second, "--now", NOW)
    assert code_one == code_two == 0
    assert "total=8" in out_one
    assert "total=1" in out_two


def test_status_first_read_only_then_apply(patrol_db, state_file, capsys):
    code, out = run(capsys, "status", "--db", patrol_db, "--state", state_file, "--now", NOW)
    assert code == 0 and "FIRST" in out
    assert not state_file.exists()
    code, out = run(
        capsys, "status", "--db", patrol_db, "--state", state_file, "--now", NOW, "--apply"
    )
    assert code == 0 and "STATE_SAVED" in out
    state = load_state(state_file)
    assert (state.last_user_msg_id, state.last_bot_msg_id) == (4, 2)


def test_status_skip_on_cooldown(patrol_db, state_file, write_state, capsys):
    write_state(last_run_ts=NOW - 100, last_user_msg_id=0, last_bot_msg_id=0)
    code, out = run(capsys, "status", "--db", patrol_db, "--state", state_file, "--now", NOW)
    assert code == 0 and "SKIP" in out and "冷却" in out


def test_status_work_digest(patrol_db, state_file, write_state, capsys):
    write_state(backfill=True, last_user_msg_id=0, last_bot_msg_id=0, last_run_ts=NOW)
    code, out = run(capsys, "status", "--db", patrol_db, "--state", state_file, "--now", NOW)
    assert code == 0
    assert "WORK" in out
    assert "BATCH_END_USER=4" in out
    assert "BATCH_END_BOT=2" in out
    assert "HAS_MORE=false" in out
    assert "---BEGIN---" in out and "---END---" in out
    assert "【尘风】" in out and "【牛杂】" in out


def test_status_work_apply_persists_boundaries(patrol_db, state_file, write_state, capsys):
    write_state(backfill=True, last_user_msg_id=0, last_bot_msg_id=0, last_run_ts=NOW)
    code, out = run(
        capsys, "status", "--db", patrol_db, "--state", state_file, "--now", NOW, "--apply"
    )
    assert code == 0 and "STATE_SAVED" in out
    state = load_state(state_file)
    assert state.pending_user_end == 4 and state.pending_bot_end == 2


def test_orphan_output(patrol_db, state_file, write_state, capsys):
    write_state()
    code, out = run(capsys, "orphan", "--db", patrol_db, "--state", state_file)
    assert code == 0 and "ORPHAN 3" in out
    assert "#1" in out and "#2" in out and "#8" in out


def test_orphan_without_state(patrol_db, state_file, capsys):
    code, out = run(capsys, "orphan", "--db", patrol_db, "--state", state_file)
    assert code == 0 and "ORPHAN_SKIP" in out


def test_audit_alert_strict_and_apply(config_dir, ledger_file, snapshot_file, write_ledger, capsys):
    write_ledger("改了 a.json，见流水\n")
    common = [
        "audit",
        "--ledger",
        ledger_file,
        "--config",
        config_dir / "*.json",
        "--audit-snapshot",
        snapshot_file,
    ]
    code, out = run(capsys, *common)
    assert code == 0 and "AUDIT_ALERT" in out
    code, _ = run(capsys, *common, "--strict")
    assert code == 1
    code, out = run(capsys, *common, "--apply")
    assert code == 0 and "AUDIT_SNAPSHOT_SAVED" in out
    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert any(path.endswith("a.json") for path in snapshot)
    assert not any(path.endswith("b.json") for path in snapshot)
    # a second --apply backs up the existing snapshot next to it (no cwd fallback)
    code, _ = run(capsys, *common, "--apply")
    assert code == 0
    assert list((snapshot_file.parent / "memorix-backups").glob("audit_snapshot.json-preaudit-*"))


def test_audit_ok_when_ledger_mentions_both(config_dir, write_ledger, snapshot_file, capsys):
    ledger = write_ledger("改了 a.json 和 b.json\n")
    code, out = run(
        capsys,
        "audit",
        "--ledger",
        ledger,
        "--config",
        config_dir / "*.json",
        "--audit-snapshot",
        snapshot_file,
    )
    assert code == 0 and "AUDIT_OK" in out


def test_audit_missing_ledger(config_dir, tmp_path, capsys):
    code, out = run(
        capsys,
        "audit",
        "--ledger",
        tmp_path / "missing.md",
        "--config",
        config_dir / "*.json",
    )
    assert code == 2 and "AUDIT_ERROR" in out


def test_intents_report_and_apply(patrol_db, capsys):
    code, out = run(capsys, "intents", "--db", patrol_db, "--now", NOW)
    assert code == 0
    assert "INTENT_EXPIRED=8" in out
    code, out = run(capsys, "intents", "--db", patrol_db, "--now", NOW, "--apply")
    assert code == 0 and "APPLIED intents=1" in out
    with SQLiteStore(patrol_db, readonly=True) as store:
        memory = store.get_memory(8)
        assert memory.memory_type == "episodic"
        assert memory.importance == 6
        assert memory.content.startswith("[意图已过期,2026-01-01]")
    assert list((patrol_db.parent / "memorix-backups").glob("*.db"))


def test_decay_report_and_apply(patrol_db, capsys):
    code, out = run(capsys, "decay", "--db", patrol_db, "--now", NOW)
    assert code == 0 and "DECAY_CANDIDATES=1" in out
    code, out = run(capsys, "decay", "--db", patrol_db, "--now", NOW, "--apply")
    assert code == 0 and "APPLIED decay=1" in out
    with SQLiteStore(patrol_db, readonly=True) as store:
        assert store.get_memory(6).importance == 1


def test_finish_refusals_and_apply(
    patrol_db, state_file, write_state, ledger_file, write_ledger, capsys
):
    write_state()
    write_ledger("### 2026-10-20 23:00 · 自动巡检\n")
    common = [
        "finish",
        "--db",
        patrol_db,
        "--state",
        state_file,
        "--ledger",
        ledger_file,
        "--user-end",
        4,
        "--bot-end",
        2,
        "--now",
        NOW,
    ]
    code, out = run(capsys, *common, "--mem-ids", "3", "--ledger-mark", "自动巡检")
    assert code == 3 and "REFUSED" in out  # memory older than last finish
    code, out = run(capsys, *common, "--mem-ids", "999", "--ledger-mark", "自动巡检")
    assert code == 3 and "不存在" in out
    code, out = run(capsys, *common, "--mem-ids", "2", "--ledger-mark", "不存在")
    assert code == 3 and "找不到" in out
    code, out = run(capsys, *common, "--mem-ids", "2", "--ledger-mark", "自动巡检")
    assert code == 0 and "FINISH_READY" in out
    code, out = run(
        capsys, *common, "--mem-ids", "2", "--ledger-mark", "自动巡检", "--apply"
    )
    assert code == 0 and "OK 游标推进" in out
    state = load_state(state_file)
    assert state.last_user_msg_id == 4 and state.last_finish_ts == NOW
    assert list((patrol_db.parent / "memorix-backups").glob("last_patrol.json-preapply-*"))


def test_finish_none_special_case(
    patrol_db, state_file, write_state, ledger_file, write_ledger, capsys
):
    write_state()
    write_ledger()
    code, out = run(
        capsys,
        "finish",
        "--db",
        patrol_db,
        "--state",
        state_file,
        "--ledger",
        ledger_file,
        "--user-end",
        4,
        "--bot-end",
        2,
        "--mem-ids",
        "none",
        "--ledger-mark",
        "none",
        "--now",
        NOW,
        "--apply",
    )
    assert code == 0 and "OK 游标推进" in out


def test_consolidate_show_and_apply_file(patrol_db, tmp_path, capsys):
    code, out = run(capsys, "consolidate", "--db", patrol_db, "--show")
    assert code == 0
    data = json.loads(out)
    assert [item["memory_id"] for item in data["candidates"]] == [6, 4, 3]

    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps([{"memory_id": 6, "theme": "项目A"}]), encoding="utf-8")
    code, out = run(capsys, "consolidate", "--db", patrol_db, "--apply-file", plan)
    assert code == 0 and "CONSOLIDATE_READY promotions=1" in out
    code, out = run(capsys, "consolidate", "--db", patrol_db, "--apply-file", plan, "--apply")
    assert code == 0 and "APPLIED promotions=1" in out
    with SQLiteStore(patrol_db, readonly=True) as store:
        memory = store.get_memory(6)
        assert memory.memory_type == "auto_patrol"
        assert memory.importance == 3


def test_consolidate_rejects_out_of_window_plan(patrol_db, tmp_path, capsys):
    plan = tmp_path / "bad.json"
    plan.write_text(json.dumps([{"memory_id": 1, "theme": "x"}]), encoding="utf-8")
    code, out = run(capsys, "consolidate", "--db", patrol_db, "--apply-file", plan)
    assert code == 2 and "PLAN_ERROR" in out


def test_missing_db_is_config_error(patrol_db, capsys):
    code, out = run(capsys, "diagnose")
    assert code == 4 and "ConfigError" in out


def test_readonly_commands_do_not_modify_db(patrol_db, state_file, write_state, capsys):
    write_state()
    before = sha256(patrol_db)
    run(capsys, "diagnose", "--db", patrol_db, "--state", state_file, "--now", NOW)
    run(capsys, "orphan", "--db", patrol_db, "--state", state_file)
    run(capsys, "decay", "--db", patrol_db, "--now", NOW)
    run(capsys, "intents", "--db", patrol_db, "--now", NOW)
    run(capsys, "status", "--db", patrol_db, "--state", state_file, "--now", NOW)
    assert sha256(patrol_db) == before


def test_finish_missing_boundary_is_refused_like_production(
    patrol_db, state_file, write_state, ledger_file, write_ledger, capsys
):
    write_state()
    write_ledger()
    code, out = run(
        capsys,
        "finish",
        "--db",
        patrol_db,
        "--state",
        state_file,
        "--ledger",
        ledger_file,
        "--mem-ids",
        "none",
        "--ledger-mark",
        "none",
    )
    assert code == 3 and "REFUSED" in out


def test_profile_command(capsys):
    code, out = run(capsys, "profile", "--list")
    assert code == 0 and "chat" in out and "project" in out and "both" in out
    code, out = run(capsys, "profile", "--name", "chat")
    assert code == 0 and "PROFILE=chat" in out


def test_finish_refuses_out_of_range_or_rewind(
    patrol_db, state_file, write_state, ledger_file, write_ledger, capsys
):
    write_state()
    write_ledger()
    common = [
        "finish",
        "--db", patrol_db,
        "--state", state_file,
        "--ledger", ledger_file,
        "--mem-ids", "none",
        "--ledger-mark", "none",
        "--now", NOW,
    ]
    code, out = run(capsys, *common, "--user-end", 99, "--bot-end", 2)
    assert code == 3 and "超出" in out
    code, out = run(capsys, *common, "--user-end", 1, "--bot-end", 2)
    assert code == 3 and "回退" in out


def test_recall_command(patrol_db, capsys):
    code, out = run(capsys, "recall", "--db", patrol_db, "--query", "语义记忆", "--json")
    assert code == 0
    data = json.loads(out)
    assert 1 in data["memory_ids"]
    assert "语义记忆" in data["text"]
    code, out = run(capsys, "recall", "--db", patrol_db, "--query", "不存在的词xyz")
    assert code == 0 and out.strip() == "(empty)"


def test_doctor(patrol_db, capsys):
    code, out = run(capsys, "doctor", "--db", patrol_db, "--json")
    assert code == 0
    data = json.loads(out)
    assert data["ok"] is True
    from memorix import __version__
    assert data["version"] == __version__
    assert data["db"]["memories"] == 8
    assert "memorix" in data["entrypoints"]


def test_doctor_text(patrol_db, capsys):
    code, out = run(capsys, "doctor", "--db", patrol_db)
    assert code == 0 and "DOCTOR_OK" in out and "memories: 8" in out
