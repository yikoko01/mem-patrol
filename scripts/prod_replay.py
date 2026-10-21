"""§10.3 six-case replay against a real DB (read-only).

Two modes:
  point  — memories as of each question's timestamp (strict, reproducible)
  full   — current snapshot (shows later self-referential memories)

Usage:
  PYTHONPATH=src python scripts/prod_replay.py \
    --db /tmp/memorix-prod/messages-snapshot-*.db \
    --schema examples/self-learning.schema.json \
    --user-id 404BE32F7C9E448DB63AC9E0658A10EB --out verify/prod-replay.md
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from memorix.retrieval.bench import GROUP_INSTRUCTION
from memorix.retrieval.score import recall, recall_scored
from memorix.retrieval.store import load_rows

SYSTEM_USER = "404BE32F7C9E448DB63AC9E0658A10EB"
CASES = [
    {
        "id": "case1-start",
        "query": "我们最开始因为什么开启这个项目，最开始的困难是什么",
        "ts": 1792510350,
        "expect_any": (19, 25, 1248),
        "top_n": 3,
    },
    {
        "id": "case2-hardest",
        "query": "这个项目最困难的阶段是什么",
        "ts": 1792511381,
        "expect_any": (19, 1248),
        "top_n": 3,
    },
    {
        "id": "case3-versions",
        "query": "为什么说 8-23 比 8-19 更难",
        "ts": 1792512098,
        "expect_any": (1248, 1255, 41, 42, 1256),
        "top_n": 5,
        "data_gap_if_missing": True,
    },
    {
        "id": "case4-ummm",
        "query": "嗯嗯",
        "ts": 1792512135,
        "forbid_type": "contract",
    },
    {
        "id": "case5-weather",
        "query": "今天天气不错",
        "ts": None,
        "expect_empty": True,
    },
    {
        "id": "case6-group-instruction",
        "query": "有没有人知道这个怎么弄？",
        "ts": None,
        "context": "群友回「格局小了」，没有展开。\n另一个群友也说了格局小了。",
        "instruction": GROUP_INSTRUCTION,
        "forbid_type": "contract",
    },
]


def private_context(db: str, user_id: str, before_ts: int | None) -> str:
    conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "select message from raw_messages where sender_id=? and group_id=sender_id "
            "and (? is null or timestamp <= ?) order by id desc limit 4",
            (user_id, before_ts, before_ts),
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(str(row["message"]) for row in rows)


def has_both_version_dates(db: str, before_ts: int | None) -> bool:
    conn = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    try:
        row = conn.execute(
            "select count(*) from memories where content like '%8-23%' and content like '%8-19%' "
            "and (? is null or created_at <= ?)",
            (None if before_ts is None else before_ts * 1000,
             None if before_ts is None else before_ts * 1000),
        ).fetchone()
    finally:
        conn.close()
    return bool(row and row[0])


def run(db: str, schema: str, user_id: str, mode: str) -> list[dict]:
    results = []
    for case in CASES:
        cutoff = case["ts"] if mode == "point" else None
        rows = load_rows(db, schema=schema, as_of_ms=(cutoff * 1000) if cutoff else None)
        context = case.get("context")
        if context is None:
            # Context is always the conversation at question time; `full` only
            # means "current memory corpus" (for post-fix validation).
            context = private_context(db, user_id, case.get("ts"))
        if case["id"] == "case5-weather":
            context = ""
        scored = recall_scored(
            case["query"],
            rows=rows,
            context=context,
            user_id=user_id,
            top_k=5,
            instruction=case.get("instruction", ""),
        )
        top = scored[:5]
        top_ids = [item.row.id for item in top]
        top_types = [item.row.memory_type for item in top]
        status = "FAIL"
        note = ""
        if case.get("expect_empty"):
            status = "PASS" if not top_ids else "FAIL"
        elif case.get("expect_any"):
            top_n = case.get("top_n", 3)
            hit = [mid for mid in top_ids[:top_n] if mid in case["expect_any"]]
            status = "PASS" if hit else "FAIL"
            if case.get("data_gap_if_missing") and not hit and not has_both_version_dates(db, cutoff):
                status = "DATA_GAP"
                note = "corpus has no memory containing both 8-23 and 8-19 before cutoff"
        else:
            ok = bool(top_ids) and not case.get("forbid_type") in top_types
            status = "PASS" if ok else "FAIL"
        results.append(
            {
                "case": case["id"],
                "status": status,
                "top_ids": top_ids,
                "top_types": top_types,
                "note": note,
                "query": case["query"],
            }
        )
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--schema", default="examples/self-learning.schema.json")
    parser.add_argument("--user-id", default=SYSTEM_USER)
    parser.add_argument("--out", help="markdown report path")
    parser.add_argument("--json", help="json output path")
    args = parser.parse_args(argv)
    all_results = {}
    for mode in ("point", "full"):
        all_results[mode] = run(args.db, args.schema, args.user_id, mode)
    passed = sum(item["status"] == "PASS" for item in all_results["point"])
    gaps = sum(item["status"] == "DATA_GAP" for item in all_results["point"])
    lines = [
        "# §10.3 production replay (read-only)",
        "",
        "DB: `%s`" % args.db,
        "schema: `%s`" % args.schema,
        "user: `%s`" % args.user_id,
        "",
        "- point mode: **%d PASS / %d DATA_GAP / %d FAIL** (of 6)"
        % (passed, gaps, 6 - passed - gaps),
        "- full mode: **%d PASS / %d FAIL**"
        % (
            sum(item["status"] == "PASS" for item in all_results["full"]),
            6 - sum(item["status"] == "PASS" for item in all_results["full"]),
        ),
        "",
        "| mode | case | status | top ids | note |",
        "|---|---|---|---|---|",
    ]
    for mode in ("point", "full"):
        for item in all_results[mode]:
            lines.append(
                "| %s | %s | %s | %s | %s |"
                % (mode, item["case"], item["status"], item["top_ids"], item["note"])
            )
    report = "\n".join(lines) + "\n"
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
