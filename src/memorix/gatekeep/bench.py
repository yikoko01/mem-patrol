"""Judge replay set (guide §5 M2 exit requirement: "有回放集").

The corpus is a JSONL file: one line per historical decision, containing the
minimal ``Context`` fields, the judge's raw JSON output and the expected
outcome. Replay never calls an LLM: the raw output stands in for the model.

Run:
    PYTHONPATH=src python -m memorix.gatekeep.bench
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .decide import decide
from .models import Context

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "judge_cases.jsonl"


@dataclass
class CaseResult:
    case_id: str
    ok: bool
    detail: str
    action: str


def load_cases(path: str | Path | None = None) -> list[dict]:
    fixture = Path(path) if path else FIXTURE_PATH
    cases = []
    with open(fixture, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def run_cases(cases: list[dict] | None = None) -> list[CaseResult]:
    cases = load_cases() if cases is None else list(cases)
    results: list[CaseResult] = []
    for case in cases:
        config = case.get("config") or {}
        ctx = Context(
            text=case.get("text", ""),
            group_id=case.get("group_id", "g1"),
            sender_id=case.get("sender_id", "u1"),
            message_id=case.get("id", "m1"),
            timestamp=case.get("timestamp", 1_800_000_000.0),
            directed=bool(case.get("directed", False)),
            scene_trigger=case.get("scene_trigger", ""),
            config=config,
        )

        raw = case.get("judge_raw")
        called = {"count": 0}

        def judge(_ctx, _raw=raw):
            called["count"] += 1
            return _raw

        outcome = decide(ctx, judge=judge)
        expected_action = case["expect_action"]
        problems = []
        if outcome.action != expected_action:
            problems.append("action %s != %s" % (outcome.action, expected_action))
        if called["count"] > 1:
            problems.append("judge called %d times" % called["count"])
        if case.get("expect_text") is not None and outcome.decision.text != case["expect_text"]:
            problems.append("text %r != %r" % (outcome.decision.text, case["expect_text"]))
        if case.get("expect_reason") and case["expect_reason"] not in outcome.reason:
            problems.append("reason %r lacks %r" % (outcome.reason, case["expect_reason"]))
        if raw is None and called["count"]:
            problems.append("judge must not be called when a gate is expected to veto")
        results.append(
            CaseResult(
                case_id=case["id"],
                ok=not problems,
                detail="; ".join(problems) if problems else "ok",
                action=outcome.action,
            )
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memorix.gatekeep.bench")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixtures", help="optional alternate JSONL corpus")
    args = parser.parse_args(argv)
    results = run_cases(load_cases(args.fixtures) if args.fixtures else None)
    if args.json:
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
    else:
        for result in results:
            print("[%s] %-28s action=%s %s" % ("PASS" if result.ok else "FAIL", result.case_id, result.action, result.detail))
        passed = sum(1 for result in results if result.ok)
        print("RESULT %d/%d passed" % (passed, len(results)))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
