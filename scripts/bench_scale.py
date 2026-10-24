"""Synthetic scaling benchmark: diagnosis/decay/recall on N memories.

Usage:
    python scripts/bench_scale.py --rows 10000
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path

from memorix.diagnose import build_diagnosis
from memorix.policy.decay import plan_decay
from memorix.retrieval.score import recall
from memorix.retrieval.store import load_rows
from memorix.store import SQLiteStore

TYPES = ("auto_patrol", "learning_gap", "episodic", "manual_remember", "contract", "progress")


def make_db(path: Path, rows: int) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "create table memories (id integer primary key, group_id text, user_id text, "
        "content text, importance integer, memory_type text, created_at integer, "
        "last_accessed integer, access_count integer, emotion text)"
    )
    base = 1_700_000_000
    payload = []
    for index in range(1, rows + 1):
        memory_type = TYPES[index % len(TYPES)]
        payload.append(
            (
                index,
                "g",
                "u",
                "合成记忆 %d：项目阶段与召回验证的上下文样本" % index,
                index % 10,
                memory_type,
                (base - index) * 1000,
                0,
                0,
                None,
            )
        )
    conn.executemany("insert into memories values (?,?,?,?,?,?,?,?,?,?)", payload)
    conn.commit()
    conn.close()


def timed(fn):
    start = time.perf_counter()
    value = fn()
    return (time.perf_counter() - start) * 1000, value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "scale.db"
        make_db(db, args.rows)
        read_ms, memories = timed(lambda: SQLiteStore(db, readonly=True).iter_memories())
        decay_ms, actions = timed(lambda: plan_decay(memories, now_ts=1_800_000_000))
        diag_ms, diagnosis = timed(lambda: build_diagnosis(memories, now=1_800_000_000))
        load_ms, rows = timed(lambda: load_rows(db))
        query = "项目阶段与召回验证"
        context = "这次我指定一个项目"
        recall(query, rows=rows, context=context, top_k=5, max_chars=900)  # warm-up
        recall_times = []
        for _ in range(3):
            ms, _ = timed(
                lambda: recall(query, rows=rows, context=context, top_k=5, max_chars=900)
            )
            recall_times.append(ms)
        recall_ms = sorted(recall_times)[len(recall_times) // 2]
    result = {
        "rows": args.rows,
        "iter_memories_ms": round(read_ms, 1),
        "plan_decay_ms": round(decay_ms, 1),
        "build_diagnosis_ms": round(diag_ms, 1),
        "load_rows_ms": round(load_ms, 1),
        "recall_ms": round(recall_ms, 1),
        "recall_warmup_runs": 3,
        "decay_actions": len(actions),
        "findings": len(diagnosis.findings),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
