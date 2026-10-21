"""M1.5 recall scorer: tokens, anchors, scoring rules, store, six-case bench."""
from __future__ import annotations

import json

import pytest

from memorix.retrieval.anchor import pick_anchor, words
from memorix.retrieval.bench import (
    AS_OF_MS,
    CASES,
    CTX_GROUP,
    EARLY,
    GROUP_INSTRUCTION,
    POST_CASE,
    fixture_rows,
    main as bench_main,
    run_bench,
    run_case,
)
from memorix.retrieval.score import recall, rank
from memorix.retrieval.store import RetrievalRow, doc_freq, load_rows
from memorix.retrieval.tokens import single_line, tokens


# ── tokens ───────────────────────────────────────────────────────────
def test_tokens_chinese_bigrams():
    assert {"石头", "头门"} <= tokens("石头门")


def test_tokens_ascii_words():
    assert {"apk", "steins_gate"} <= tokens("APK steins_gate")


def test_tokens_empty():
    assert tokens("") == set()
    assert tokens(None) == set()


def test_single_line_collapses_and_truncates():
    assert single_line("  a\n b  ", 10) == "a b"
    assert single_line("abcdef", 3) == "abc"


# ── anchor ───────────────────────────────────────────────────────────
def test_words_requires_jieba():
    pytest.importorskip("jieba")
    found = words("[At:qq_official] 这次我指定一个，石头门")
    assert "石头" in found  # '[At:...]' residue stripped, noun kept


def test_pick_anchor_newest_first():
    pytest.importorskip("jieba")
    rows = fixture_rows()
    df = doc_freq(rows)
    context = "我在做记忆召回验证，这次我指定一个，石头门\n我们上次抄腾讯架构"
    anchor = pick_anchor(context, tokens("这个项目最困难的阶段是什么"), df)
    assert anchor == "石头"


def test_pick_anchor_skips_generic_words():
    pytest.importorskip("jieba")
    rows = fixture_rows()
    df = doc_freq(rows)
    assert pick_anchor("这个项目的内容和阶段", tokens("x"), df) == ""


def test_pick_anchor_without_jieba_is_empty(monkeypatch):
    import memorix.retrieval.anchor as anchor_module

    monkeypatch.setattr(anchor_module, "_JIEBA_TRIED", True)
    monkeypatch.setattr(anchor_module, "_JIEBA", None)
    assert words("石头门") == []
    assert pick_anchor("这次我指定一个，石头门", tokens("x"), {}) == ""


# ── scoring ──────────────────────────────────────────────────────────
def test_instruction_is_never_matched():
    rows = fixture_rows()
    without = recall("有没有人知道这个怎么弄？", rows=rows, context=CTX_GROUP, top_k=5)
    with_instruction = recall(
        "有没有人知道这个怎么弄？",
        rows=rows,
        context=CTX_GROUP,
        top_k=5,
        instruction=GROUP_INSTRUCTION,
    )
    assert with_instruction == without


def test_contract_not_pulled_without_anchor():
    pytest.importorskip("jieba")
    rows = fixture_rows()
    scored = rank("今天天气不错", rows=rows, doc_freq=doc_freq(rows))
    assert all(item.row.memory_type != "contract" for item in scored)


def test_weather_smalltalk_returns_empty():
    rows = fixture_rows()
    assert recall("今天天气不错", rows=rows) == ""


def test_user_isolation():
    rows = fixture_rows()
    other = RetrievalRow(
        id=7777,
        content="石头门项目的私密记录",
        memory_type="episodic",
        importance=9,
        created_at=1_000_000,
        group_id="g",
        user_id="someone-else",
        tokens=frozenset(tokens("石头门项目的私密记录")),
    )
    rows = rows + [other]
    ranked = rank(
        "这个项目最困难的阶段是什么",
        rows=rows,
        doc_freq=doc_freq(rows),
        context="这次我指定一个，石头门",
        user_id="owner",
    )
    assert 7777 not in [item.row.id for item in ranked]


def test_top_k_caps_output_lines():
    rows = fixture_rows()
    text = recall("这个项目最困难的阶段是什么", rows=rows, context="这次我指定一个，石头门", top_k=2)
    assert len([line for line in text.splitlines() if line]) <= 2


def test_recall_formatting():
    rows = fixture_rows()
    text = recall("这个项目最困难的阶段是什么", rows=rows, context="这次我指定一个，石头门")
    assert text.startswith("- [")
    assert "石头门" in text


# ── store ────────────────────────────────────────────────────────────
def test_load_rows_and_as_of(make_patrol_db):
    db = make_patrol_db(
        memories=[
            (1, "auto_patrol", 7, 1_700_000_000_000, "旧记忆", "g", "u"),
            (2, "auto_patrol", 7, 1_800_000_000_000, "新记忆", "g", "u"),
            (3, "archived", 1, 1_700_000_000_000, "归档", "g", "u"),
        ],
        raw=[],
        bot=[],
    )
    rows = load_rows(db)
    assert {row.id for row in rows} == {1, 2}  # archived excluded
    assert [row.id for row in load_rows(db, as_of_ms=1_750_000_000_000)] == [1]
    frequencies = doc_freq(rows)
    assert frequencies["记忆"] == 2


def test_load_rows_missing_db(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_rows(tmp_path / "nope.db")


# ── §10.3 six-case bench ─────────────────────────────────────────────
def test_bench_fixture_all_six_pass():
    pytest.importorskip("jieba")
    results = run_bench()
    failed = [result for result in results if not result.ok]
    assert not failed, [(result.case_id, result.detail) for result in failed]
    assert len(results) == 6


@pytest.mark.parametrize("case", CASES, ids=[case.case_id for case in CASES])
def test_bench_each_case(case):
    pytest.importorskip("jieba")
    result = run_case(case, fixture_rows())
    assert result.ok, result.detail


def test_bench_cli(capsys):
    pytest.importorskip("jieba")
    assert bench_main([]) == 0
    out = capsys.readouterr().out
    assert "RESULT 6/6 passed" in out


def test_bench_cli_db_requires_as_of(tmp_path, capsys):
    assert bench_main(["--db", str(tmp_path / "x.db")]) == 2
    assert "requires --as-of-ms" in capsys.readouterr().out


def test_bench_json(capsys):
    pytest.importorskip("jieba")
    assert bench_main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 6
    assert all(item["ok"] for item in payload)


# ── individual rules (each must be killable on its own) ──────────────
def test_no_anchor_coverage_floor_blocks_common_token():
    common = RetrievalRow(
        id=8801,
        content="这个说法不错",
        memory_type="auto_patrol",
        importance=9,
        created_at=EARLY,
        group_id="",
        user_id="",
        tokens=frozenset(tokens("这个说法不错")),
    )
    rows = fixture_rows() + [common]
    # no anchor (no context) + only common-token overlap -> must stay empty
    assert recall("今天天气不错", rows=rows) == ""


def test_contract_is_not_selected_without_anchor_hit():
    rows = fixture_rows()
    frequencies = doc_freq(rows)
    query = "约定的检索偏好是什么"
    no_anchor = rank(query, rows=rows, doc_freq=frequencies, context="")
    assert all(item.row.memory_type != "contract" for item in no_anchor)
    with_anchor = rank(
        query, rows=rows, doc_freq=frequencies, context="这次我指定一个，石头门"
    )
    assert all(item.row.memory_type != "contract" for item in with_anchor)


def test_instruction_does_not_change_scores():
    rows = fixture_rows()
    frequencies = doc_freq(rows)
    without = rank(
        "有没有人知道这个怎么弄？",
        rows=rows,
        doc_freq=frequencies,
        context=CTX_GROUP,
        top_k=5,
    )
    with_instruction = rank(
        "有没有人知道这个怎么弄？",
        rows=rows,
        doc_freq=frequencies,
        context=CTX_GROUP,
        top_k=5,
        instruction=GROUP_INSTRUCTION,
    )
    assert [(item.row.id, item.score) for item in with_instruction] == [
        (item.row.id, item.score) for item in without
    ]


def test_as_of_excludes_later_memories():
    # Deliberately replay case1 *after* the post-case memory exists: the
    # expectation must fail because 9300 leaks in.
    result = run_case(CASES[0], fixture_rows(), as_of_ms=POST_CASE * 1000)
    assert not result.ok
    assert 9300 in result.top_ids


def test_bench_db_mode_threads_as_of(tmp_path, make_patrol_db, capsys):
    base = 1_792_510_000
    cut_ms = 1_792_520_000_000
    post = 1_792_530_000
    rows = fixture_rows()
    memories = []
    for row in rows:
        created = post if row.created_at == POST_CASE else base
        memories.append(
            (row.id, row.memory_type, row.importance, created, row.content, row.group_id, row.user_id)
        )
    db = make_patrol_db(memories=memories, raw=[], bot=[])
    code = bench_main(["--db", str(db), "--as-of-ms", str(cut_ms)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "RESULT 6/6 passed" in out


def test_ascii_anchor_is_lowercased_and_matched():
    pytest.importorskip("jieba")
    rows = [
        RetrievalRow(
            id=1,
            content="Steins Gate 项目的破解记录",
            memory_type="auto_patrol",
            importance=8,
            created_at=EARLY,
            group_id="",
            user_id="",
            tokens=frozenset(tokens("Steins Gate 项目的破解记录")),
        ),
        RetrievalRow(
            id=2,
            content="Steins 相关的另一个记录",
            memory_type="auto_patrol",
            importance=8,
            created_at=EARLY,
            group_id="",
            user_id="",
            tokens=frozenset(tokens("Steins 相关的另一个记录")),
        ),
        RetrievalRow(
            id=3,
            content="无关项目",
            memory_type="auto_patrol",
            importance=8,
            created_at=EARLY,
            group_id="",
            user_id="",
            tokens=frozenset(tokens("无关项目")),
        ),
    ]
    frequencies = doc_freq(rows)
    context = "上次我指定一个 STEINS 项目"
    anchor = pick_anchor(context, tokens("这个项目的困难"), frequencies)
    assert anchor and anchor.lower() == "steins"
    ranked = rank("这个项目", rows=rows, doc_freq=frequencies, context=context)
    assert ranked and ranked[0].row.id in {1, 2} and ranked[0].anchor_hit


def test_multi_char_cjk_anchor_matches_bigrams():
    pytest.importorskip("jieba")
    rows = [
        RetrievalRow(1, "腾讯云项目的部署记录", "auto_patrol", 8, EARLY, "", "", frozenset(tokens("腾讯云项目的部署记录"))),
        RetrievalRow(2, "腾讯云项目的第二份记录", "auto_patrol", 8, EARLY, "", "", frozenset(tokens("腾讯云项目的第二份记录"))),
        RetrievalRow(3, "无关项目", "auto_patrol", 8, EARLY, "", "", frozenset(tokens("无关项目"))),
    ]
    frequencies = doc_freq(rows)
    context = "上次说的腾讯云项目"
    anchor = pick_anchor(context, tokens("这个项目"), frequencies)
    assert anchor
    ranked = rank("这个项目", rows=rows, doc_freq=frequencies, context=context)
    assert ranked and ranked[0].row.id in {1, 2}


def test_bench_db_mode_empty_corpus_is_not_vacuous(tmp_path, make_patrol_db, capsys):
    db = make_patrol_db(
        memories=[(1, "auto_patrol", 7, 1_792_510_000_000, "无关内容", "g", "u")],
        raw=[],
        bot=[],
    )
    code = bench_main(["--db", str(db), "--as-of-ms", str(1_792_520_000_000)])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "expected non-empty" in out

# ── M3 metrics integration ──────────────────────────────────────────
def test_recall_records_metrics():
    from memorix.observability import MetricsCollector

    collector = MetricsCollector()
    text = recall(
        "这个项目最困难的阶段是什么",
        rows=fixture_rows(),
        context="这次我指定一个，石头门",
        metrics=collector,
        source="g1",
    )
    assert text
    snapshot = collector.snapshot()
    assert snapshot["by_kind"] == {"recall": 1}
    assert snapshot["outcomes"] == {"recall:hit": 1}
