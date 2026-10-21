"""M3 offline evaluation: suites, baseline regression, CLI."""
from __future__ import annotations

import json

import pytest

from memorix.eval import runner
from memorix.eval.runner import (
    CaseOutcome,
    EvalReport,
    SuiteOutcome,
    compare,
    main,
    run_all,
    run_suite,
)


def test_policy_suite_passes():
    suite = run_suite("policy")
    failed = [case for case in suite.cases if not case.ok]
    assert not failed, [(case.case_id, case.detail) for case in failed]
    assert suite.name == "policy"


@pytest.mark.parametrize("name", ["recall", "judge"])
def test_replay_suites_pass(name):
    pytest.importorskip("jieba")
    suite = run_suite(name)
    assert suite.failed == 0, [(case.case_id, case.detail) for case in suite.cases]
    assert suite.passed > 0


def test_run_all_and_report_roundtrip():
    pytest.importorskip("jieba")
    report = run_all()
    assert report.failed == 0
    data = report.to_dict()
    restored = EvalReport.from_dict(data)
    assert restored.to_dict()["suites"] == data["suites"]
    assert restored.passed == report.passed


def test_compare_no_regression():
    report = EvalReport((SuiteOutcome("s", (CaseOutcome("a", True),)),))
    baseline = report.to_dict()
    assert compare(report, baseline) == []


def test_compare_detects_regression():
    baseline = {
        "version": 1,
        "suites": {"s": {"cases": {"a": True, "b": True}}},
    }
    report = EvalReport(
        (SuiteOutcome("s", (CaseOutcome("a", True), CaseOutcome("b", False))),)
    )
    assert compare(report, baseline) == ["s/b"]


def test_compare_detects_missing_case_and_suite():
    baseline = {
        "version": 1,
        "suites": {
            "s": {"cases": {"a": True, "gone": True}},
            "whole": {"cases": {"x": True}},
        },
    }
    report = EvalReport((SuiteOutcome("s", (CaseOutcome("a", True),)),))
    regressions = compare(report, baseline)
    assert "s/gone (case missing)" in regressions
    assert "whole (suite missing)" in regressions


def test_cli_update_baseline_and_pass(tmp_path):
    baseline = tmp_path / "baseline.json"
    out = tmp_path / "report.json"
    assert main(["--suite", "policy", "--baseline", str(baseline), "--out", str(out), "--update-baseline"]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["suites"]["policy"]["failed"] == 0
    assert baseline.exists()
    assert main(["--suite", "policy", "--baseline", str(baseline), "--out", str(out)]) == 0


def test_cli_detects_regression(tmp_path, monkeypatch, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"version": 1, "suites": {"policy": {"cases": {"x": True}}}}),
        encoding="utf-8",
    )
    failing = SuiteOutcome("policy", (CaseOutcome("x", False, "boom"),))
    monkeypatch.setattr(runner, "run_suite", lambda name: failing)
    assert main(["--suite", "policy", "--baseline", str(baseline)]) == 1
    assert "REGRESSIONS" in capsys.readouterr().out


def test_cli_failure_exit(tmp_path, monkeypatch):
    failing = SuiteOutcome("policy", (CaseOutcome("x", False, "boom"),))
    monkeypatch.setattr(runner, "run_suite", lambda name: failing)
    assert main(["--suite", "policy", "--baseline", str(tmp_path / "none.json")]) == 1

def test_shipped_baseline_exists_and_passes():
    pytest.importorskip("jieba")
    from memorix.eval.runner import load_baseline

    baseline = load_baseline()
    assert baseline.get("suites"), "eval/baseline.json must be shipped"
    report = run_all()
    assert report.failed == 0
    assert compare(report, baseline) == []


def test_update_baseline_refuses_red_report(tmp_path, monkeypatch, capsys):
    failing = SuiteOutcome("policy", (CaseOutcome("x", False, "boom"),))
    monkeypatch.setattr(runner, "run_suite", lambda name: failing)
    baseline = tmp_path / "baseline.json"
    assert main(["--suite", "policy", "--baseline", str(baseline), "--update-baseline"]) == 1
    assert not baseline.exists()
    assert "BASELINE_SKIPPED" in capsys.readouterr().out


def test_single_suite_ignores_other_baseline_suites(tmp_path):
    pytest.importorskip("jieba")
    baseline = tmp_path / "baseline.json"
    assert main(["--suite", "all", "--baseline", str(baseline), "--update-baseline"]) == 0
    # A policy-only run must not flag the recall/judge baseline suites as missing.
    assert main(["--suite", "policy", "--baseline", str(baseline)]) == 0
