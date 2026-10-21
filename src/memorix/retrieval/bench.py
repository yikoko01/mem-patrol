"""§10.3 replay bench for the recall scorer.

Six cases from the guide, with a deterministic fixture corpus. Each case is run
as of a point in time so memories written after the historical question cannot
leak into the result (that is what made the production baseline unreproducible).

Run:
    PYTHONPATH=src python -m memorix.retrieval.bench
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

from .score import format_scored, rank, recall
from .store import RetrievalRow, doc_freq, load_rows
from .tokens import single_line, tokens

EARLY = 1_000_000  # epoch seconds: before every case
AS_OF_MS = 5_000_000 * 1000  # after EARLY, before POST_CASE
POST_CASE = 9_000_000  # a memory written after the cases (must be excluded)

CTX_PRIVATE = "\n".join(
    [
        "[At:qq_official] 我在做记忆召回验证，我需要你再看看之前项目内容，这次我指定一个，石头门",
        "[At:qq_official] 还在修，你再看看之前项目的修改",
        "[At:qq_official] 我们上次抄腾讯架构些什么啊？然后新架构要抄的你改了没？",
    ]
)
CTX_GROUP = "群友回「格局小了」，没有展开。\n另一个群友也说了格局小了。"
GROUP_INSTRUCTION = (
    "群聊主动插话判断：群=3AF8FB0F0CDF328982102635F711638C；触发消息=有没有人知道这个怎么弄？；"
    "群聊最近谁在对话、谁不喜欢被cue、上次插话效果、关系边界、常聊话题、是否适合轻接一句"
)


@dataclass(frozen=True)
class BenchCase:
    case_id: str
    query: str
    context: str
    as_of_ms: int = AS_OF_MS
    instruction: str = ""
    expect_first: int | None = None
    expect_in_top: int | None = None
    expect_top_n: int = 3
    expect_empty: bool = False
    expect_non_empty: bool = False
    expect_absent: int | None = None
    forbid_type: str | None = None


CASES = (
    BenchCase(
        "case1-start",
        "我们最开始因为什么开启这个项目，最开始的困难是什么",
        CTX_PRIVATE,
        expect_non_empty=True,
        expect_absent=9300,
        expect_in_top=9102,
    ),
    BenchCase(
        "case2-hardest",
        "这个项目最困难的阶段是什么",
        CTX_PRIVATE,
        expect_non_empty=True,
        expect_absent=9300,
        expect_first=9101,
    ),
    BenchCase(
        "case3-versions",
        "为什么说 8-23 比 8-19 更难",
        CTX_PRIVATE,
        expect_non_empty=True,
        expect_absent=9300,
        expect_in_top=9103,
        expect_top_n=2,
    ),
    BenchCase(
        "case4-ummm",
        "嗯嗯",
        CTX_PRIVATE,
        expect_absent=9300,
        forbid_type="contract",
    ),
    BenchCase(
        "case5-weather",
        "今天天气不错",
        "",
        expect_empty=True,
    ),
    BenchCase(
        "case6-group-instruction",
        "有没有人知道这个怎么弄？",
        CTX_GROUP,
        instruction=GROUP_INSTRUCTION,
        forbid_type="contract",
    ),
)


def _row(
    memory_id: int,
    content: str,
    memory_type: str = "auto_patrol",
    importance: int = 7,
    created_at: int = EARLY,
    group_id: str = "",
    user_id: str = "",
) -> RetrievalRow:
    return RetrievalRow(
        id=memory_id,
        content=single_line(content, 600),
        memory_type=memory_type,
        importance=importance,
        created_at=created_at,
        group_id=group_id,
        user_id=user_id,
        tokens=frozenset(tokens(content)),
    )


def fixture_rows() -> list[RetrievalRow]:
    """Deterministic corpus for the six cases (mirrors the production memories)."""
    return [
        _row(
            9101,
            "石头门项目=《命运石之门》(Steins;Gate) APK 破解打包。这个项目最困难阶段=8-23 盲改期；"
            "8-23 比 8-19 更难。",
            memory_type="manual_remember",
            importance=9,
        ),
        _row(
            9102,
            "【石头门起点与最开始困难】开启这个项目的原因=他想在手机上玩汉化版；"
            "2026-08-16 11:50 他报 Android 16 打不开，最开始困难=安装校验提示。",
            importance=8,
        ),
        _row(
            9103,
            "【石头门版本对比】8-19 的坑是 scoped storage（根因明确）；8-23 是盲改期，"
            "未知闪退反复，所以 8-23 比 8-19 更难。",
            importance=8,
        ),
        _row(
            9900,
            "【记忆架构升级】腾讯记忆引擎/召回/阶段评估，与石头门项目无关。",
            importance=8,
        ),
        _row(9901, "【记忆架构考据】从修 bug 拐到项目阶段评估。", memory_type="episodic"),
        _row(
            9700,
            "【契约·检索/约定/偏好】凡事先查检索；关系边界与偏好要记住；他说不错。",
            memory_type="contract",
            importance=9,
        ),
        _row(9501, "【群聊插曲】群友回「格局小了」，没有展开。", memory_type="episodic"),
        _row(9502, "【群聊续】另一个群友也说格局小了。", memory_type="episodic"),
        _row(
            9300,
            "【用例之后才写入的记忆】记忆架构升级汇报+石头门召回验证：最开始开启这个项目的困难与阶段，"
            "项目架构升级；这条不该出现在任何一条回放里。",
            importance=8,
            created_at=POST_CASE,
        ),
    ]


@dataclass
class CaseResult:
    case_id: str
    ok: bool
    detail: str
    top_ids: list[int]


def run_case(
    case: BenchCase,
    rows: list[RetrievalRow],
    *,
    as_of_ms: int | None = None,
    check_expectations: bool = True,
) -> CaseResult:
    cut = case.as_of_ms if as_of_ms is None else int(as_of_ms)
    as_of_rows = [row for row in rows if row.created_at * 1000 <= cut]
    frequencies = doc_freq(as_of_rows)
    scored = rank(
        case.query,
        rows=as_of_rows,
        doc_freq=frequencies,
        context=case.context,
        top_k=5,
        instruction=case.instruction,
    )
    top_ids = [item.row.id for item in scored]
    text = format_scored(scored)

    problems: list[str] = []
    if check_expectations:
        if case.expect_absent is not None and case.expect_absent in top_ids:
            problems.append("later memory %s leaked into the result" % case.expect_absent)
    if case.expect_empty and text:
        problems.append("expected empty, got %d chars (top=%s)" % (len(text), top_ids[:3]))
    if check_expectations and not case.expect_empty and case.expect_first is not None:
        if not top_ids or top_ids[0] != case.expect_first:
            problems.append("expected first=%s, got %s" % (case.expect_first, top_ids[:3]))
    if check_expectations and case.expect_in_top is not None:
        if case.expect_in_top not in top_ids[: case.expect_top_n]:
            problems.append(
                "expected %s in top%d, got %s"
                % (case.expect_in_top, case.expect_top_n, top_ids[: case.expect_top_n])
            )
    if case.expect_non_empty and not scored:
        problems.append("expected non-empty results")
    if case.forbid_type is not None:
        bad = [item.row.id for item in scored if item.row.memory_type == case.forbid_type]
        if bad:
            problems.append("forbidden type %s appeared: %s" % (case.forbid_type, bad[:3]))
    if case.instruction:
        without_instruction = rank(
            case.query,
            rows=as_of_rows,
            doc_freq=frequencies,
            context=case.context,
            top_k=5,
        )
        with_instruction = rank(
            case.query,
            rows=as_of_rows,
            doc_freq=frequencies,
            context=case.context,
            top_k=5,
            instruction=case.instruction,
        )
        if [(item.row.id, round(item.score, 6)) for item in with_instruction] != [
            (item.row.id, round(item.score, 6)) for item in without_instruction
        ]:
            problems.append("instruction changed the ranking (must be ignored)")

    return CaseResult(
        case_id=case.case_id,
        ok=not problems,
        detail="; ".join(problems) if problems else "ok",
        top_ids=top_ids[:5],
    )


def run_bench(
    rows: list[RetrievalRow] | None = None,
    *,
    as_of_ms: int | None = None,
    check_expectations: bool = True,
) -> list[CaseResult]:
    rows = fixture_rows() if rows is None else list(rows)
    return [
        run_case(
            case,
            rows,
            as_of_ms=as_of_ms,
            check_expectations=check_expectations,
        )
        for case in CASES
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memorix.retrieval.bench")
    parser.add_argument("--db", help="optional real database; needs --as-of-ms")
    parser.add_argument("--as-of-ms", type=int, help="epoch-ms cut applied to every case in --db mode")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.db:
        if not args.as_of_ms:
            print("ERROR --db requires --as-of-ms (replay must be point-in-time)")
            return 2
        rows = load_rows(args.db, as_of_ms=args.as_of_ms)
        # Fixture ids (9101...) do not exist in a real DB; keep the behavioural
        # checks (empty / forbidden type / instruction invariance) only.
        results = run_bench(rows, as_of_ms=args.as_of_ms, check_expectations=False)
    else:
        rows = fixture_rows()
        results = run_bench(rows)
    if args.json:
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result.ok else "FAIL"
            print("[%s] %-24s top=%s %s" % (status, result.case_id, result.top_ids, result.detail))
        passed = sum(1 for result in results if result.ok)
        print("RESULT %d/%d passed" % (passed, len(results)))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
