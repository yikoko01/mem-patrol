"""Offline evaluation: recall + judge + policy replay, with baseline regression.

Exit code 1 when a case fails or a previously-passing case regresses.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..gatekeep.bench import load_cases as load_judge_cases
from ..gatekeep.bench import run_cases as run_judge
from ..models import FileState, MemoryRecord
from ..policy.audit import classify_audit
from ..policy.consolidation import validate_plan
from ..policy.decay import plan_decay
from ..policy.finish_gate import verify_finish
from ..policy.intents import classify_intents, plan_intent_expiry
from ..policy.orphan import detect_orphans
from ..policy.timeparse import parse_ts
from ..retrieval.bench import fixture_rows as recall_fixture_rows
from ..retrieval.bench import run_bench as run_recall

NOW = 1_800_000_000
DEFAULT_BASELINE = Path(__file__).with_name("baseline.json")  # shipped in the package
REPO_BASELINE = Path(__file__).resolve().parents[3] / "eval" / "baseline.json"


@dataclass(frozen=True)
class CaseOutcome:
    case_id: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class SuiteOutcome:
    name: str
    cases: tuple[CaseOutcome, ...]

    @property
    def passed(self) -> int:
        return sum(1 for case in self.cases if case.ok)

    @property
    def failed(self) -> int:
        return len(self.cases) - self.passed


@dataclass(frozen=True)
class EvalReport:
    suites: tuple[SuiteOutcome, ...]

    @property
    def passed(self) -> int:
        return sum(suite.passed for suite in self.suites)

    @property
    def failed(self) -> int:
        return sum(suite.failed for suite in self.suites)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "generated_at": int(time.time()),
            "suites": {
                suite.name: {
                    "passed": suite.passed,
                    "failed": suite.failed,
                    "cases": {case.case_id: case.ok for case in suite.cases},
                }
                for suite in self.suites
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EvalReport":
        suites = []
        for name, payload in (data.get("suites") or {}).items():
            cases = tuple(
                CaseOutcome(case_id, bool(ok))
                for case_id, ok in (payload.get("cases") or {}).items()
            )
            suites.append(SuiteOutcome(name, cases))
        return cls(tuple(suites))


def _check(case_id: str, fn, outcomes: list[CaseOutcome]) -> None:
    try:
        fn()
    except AssertionError as exc:
        outcomes.append(CaseOutcome(case_id, False, "assertion: %s" % exc))
    except Exception as exc:  # noqa: BLE001 - a case failure must not stop the suite
        outcomes.append(CaseOutcome(case_id, False, "%s: %s" % (type(exc).__name__, exc)))
    else:
        outcomes.append(CaseOutcome(case_id, True))


def _policy_cases() -> SuiteOutcome:
    outcomes: list[CaseOutcome] = []

    def ts_case():
        assert parse_ts(NOW * 1000) == NOW
        assert parse_ts(NOW) == NOW
        assert parse_ts("not-a-date") == 0

    def orphan_case():
        rows = [
            MemoryRecord(1, "auto_patrol", 7, (NOW - 1000) * 1000),
            MemoryRecord(2, "auto_patrol", 7, (NOW - 100) * 1000),
        ]
        assert [item.memory_id for item in detect_orphans(rows, NOW - 500)] == [2]

    def decay_case():
        rows = [MemoryRecord(1, "episodic", 3, (NOW - 31 * 86400) * 1000)]
        actions = plan_decay(rows, NOW)
        assert len(actions) == 1 and actions[0].new_importance == 2

    def contract_exempt_case():
        rows = [MemoryRecord(1, "contract", 3, (NOW - 999 * 86400) * 1000)]
        assert plan_decay(rows, NOW) == []

    def intent_case():
        report = classify_intents(
            [MemoryRecord(1, "intent", 8, NOW, "【意图·有效期至 2020-01-01】x")],
            datetime.date(2026, 10, 21),
        )
        assert len(report.expired) == 1
        update = plan_intent_expiry(report)[0]
        assert update.memory_type == "episodic" and update.importance == 6

    def finish_none_case():
        assert verify_finish(["none"], "none", memories_by_id={}, ledger_text=None) == []

    def finish_refusal_case():
        errors = verify_finish(
            ["3"], "x", memories_by_id={}, ledger_text="x", prev_finish_ts=NOW
        )
        assert errors and "不存在" in errors[0]

    def audit_case():
        files = [FileState("/tmp/a.json", "aaa", 2000)]
        result = classify_audit({"/tmp/a.json": "aaa"}, files, "", 1000)
        assert result.benign and result.suspicious == ()

    def consolidation_case():
        rows = [
            MemoryRecord(1, "episodic", 7, NOW, "石头门"),
            MemoryRecord(2, "episodic", 8, NOW, "石头门"),
        ]
        promotions, errors = validate_plan(rows, [{"memory_id": 2, "theme": "石头门"}])
        assert not errors and promotions[0].new_importance == 9

    for case_id, fn in [
        ("parse-ts", ts_case),
        ("orphan", orphan_case),
        ("decay", decay_case),
        ("decay-contract-exempt", contract_exempt_case),
        ("intent-expiry", intent_case),
        ("finish-none", finish_none_case),
        ("finish-refusal", finish_refusal_case),
        ("audit-benign", audit_case),
        ("consolidation-validate", consolidation_case),
    ]:
        _check(case_id, fn, outcomes)
    return SuiteOutcome("policy", tuple(outcomes))


def _suite_from_bench(name: str, results) -> SuiteOutcome:
    return SuiteOutcome(
        name,
        tuple(CaseOutcome(result.case_id, bool(result.ok), result.detail) for result in results),
    )


def run_suite(name: str) -> SuiteOutcome:
    if name == "recall":
        return _suite_from_bench("recall", run_recall(recall_fixture_rows()))
    if name == "judge":
        return _suite_from_bench("judge", run_judge(load_judge_cases()))
    if name == "policy":
        return _policy_cases()
    raise ValueError("unknown suite: %r (choose recall/judge/policy/all)" % name)


def run_all() -> EvalReport:
    return EvalReport(tuple(run_suite(name) for name in ("recall", "judge", "policy")))


def load_baseline(path: str | Path | None = DEFAULT_BASELINE) -> dict:
    if path is None:
        return {}
    path = Path(path)
    if not path.exists() and path == DEFAULT_BASELINE and REPO_BASELINE.exists():
        path = REPO_BASELINE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compare(
    report: EvalReport,
    baseline: dict,
    *,
    suites: set[str] | None = None,
) -> list[str]:
    """Return human-readable regressions (previously passing cases now failing).

    ``suites`` restricts the comparison to the suites actually requested (a
    single-suite run must not flag the other baseline suites as "missing").
    """
    regressions: list[str] = []
    baseline_suites = (baseline or {}).get("suites") or {}
    report_suites = {suite.name: suite for suite in report.suites}
    for suite_name, payload in baseline_suites.items():
        if suites is not None and suite_name not in suites:
            continue
        if suite_name not in report_suites:
            regressions.append("%s (suite missing)" % suite_name)
            continue
        baseline_cases = (payload or {}).get("cases") or {}
        current = {case.case_id: case.ok for case in report_suites[suite_name].cases}
        for case_id, was_ok in baseline_cases.items():
            if case_id not in current:
                regressions.append("%s/%s (case missing)" % (suite_name, case_id))
            elif was_ok and not current[case_id]:
                regressions.append("%s/%s" % (suite_name, case_id))
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memorix.eval")
    parser.add_argument("--suite", default="all", choices=["all", "recall", "judge", "policy"])
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--out", help="write the JSON report here")
    parser.add_argument("--update-baseline", action="store_true", help="write the report as the new baseline")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = run_all() if args.suite == "all" else EvalReport((run_suite(args.suite),))
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for suite in report.suites:
            print("[%s] passed=%d failed=%d" % (suite.name, suite.passed, suite.failed))
            for case in suite.cases:
                if not case.ok:
                    print("  FAIL %s: %s" % (case.case_id, case.detail))
        print("RESULT %d/%d passed" % (report.passed, report.passed + report.failed))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    baseline_path = Path(args.baseline) if args.baseline else None
    if args.update_baseline and baseline_path is not None:
        if report.failed:
            print("BASELINE_SKIPPED %s (report has failures; refusing to bless a red baseline)" % baseline_path)
        else:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            print("BASELINE_UPDATED %s" % baseline_path)

    requested = None if args.suite == "all" else {args.suite}
    regressions = compare(report, load_baseline(baseline_path), suites=requested)
    if regressions:
        print("REGRESSIONS: %s" % ", ".join(regressions))
    return 1 if report.failed or regressions else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
