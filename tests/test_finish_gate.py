"""Finish gate: production error strings and refusal order, verbatim."""
from __future__ import annotations

from memorix.policy.finish_gate import verify_finish

LEDGER = "### 2026-10-20 23:00 · 自动巡检\n正文\n"
MEMORIES = {
    1: {"id": 1, "memory_type": "auto_patrol", "created_at": 1000},
    2: {"id": 2, "memory_type": "auto_patrol", "created_at": 2000},
}


def gate(mem_ids, ledger_mark, **overrides):
    kwargs = dict(
        memories_by_id=MEMORIES,
        ledger_text=LEDGER,
        prev_finish_ts=1500,
    )
    kwargs.update(overrides)
    return verify_finish(mem_ids, ledger_mark, **kwargs)


def test_missing_mem_ids_is_refused():
    errors = gate(None, "自动巡检")
    assert len(errors) == 1 and errors[0].startswith("缺 --mem-ids")


def test_empty_mem_ids_is_refused():
    assert gate([], "自动巡检") == ["--mem-ids 为空"]


def test_none_special_case_passes_with_none_ledger():
    assert gate(["none"], "none") == []


def test_missing_memory_is_refused():
    errors = gate(["3"], "自动巡检")
    assert errors == ["记忆 #3 不存在——先落库，再来收尾"]


def test_memory_older_than_previous_finish_is_refused():
    errors = gate(["1"], "自动巡检")
    assert errors == ["记忆 #1 写入时间早于上轮收尾，不像是本轮新写的"]


def test_fresh_memory_passes():
    assert gate(["2"], "自动巡检") == []


def test_no_previous_finish_skips_time_check():
    assert gate(["1"], "自动巡检", prev_finish_ts=0) == []


def test_missing_ledger_file_is_refused():
    errors = gate(["2"], "自动巡检", ledger_text=None, ledger_path="/tmp/history.md")
    assert errors == ["台账文件不存在：/tmp/history.md"]


def test_ledger_mark_not_found_is_refused():
    errors = gate(["2"], "不存在的小标题")
    assert errors == ["台账里找不到「不存在的小标题」——先记账，再来收尾"]


def test_lexically_equivalent_missing_arguments_report_all_errors():
    errors = gate(None, None)
    assert len(errors) == 2
    assert errors[0].startswith("缺 --mem-ids")
    assert errors[1].startswith("缺 --ledger")


def test_string_ids_resolve_against_int_keyed_rows():
    assert gate(["2"], "自动巡检") == []
    assert gate([2], "自动巡检") == []


def test_numeric_text_id_matches_sqlite_affinity():
    # SQLite compares id INTEGER to '1.0' numerically; the kernel mirrors that.
    assert gate(["1.0"], "自动巡检", prev_finish_ts=0) == []


def test_non_integer_numeric_text_id_does_not_match():
    # SQLite numeric affinity: '1.9' becomes 1.9, which does not equal id 1.
    assert gate(["1.9"], "自动巡检", prev_finish_ts=0) == ["记忆 #1.9 不存在——先落库，再来收尾"]
