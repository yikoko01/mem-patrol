"""Config-audit snapshot diff: content fingerprint first, ledger mention second."""
from __future__ import annotations

from memorix.models import FileState
from memorix.policy.audit import AUDIT_MTIME_TOLERANCE, classify_audit, ledger_mentions


def state(path, md5, mtime=100.0):
    return FileState(path=path, md5=md5, mtime=mtime)


def test_unchanged_content_and_old_mtime_is_silent():
    result = classify_audit({"/tmp/a.json": "aaa"}, [state("/tmp/a.json", "aaa", 100)], "", 1000)
    assert result.suspicious == ()
    assert result.benign == ()
    assert result.snapshot["/tmp/a.json"] == "aaa"


def test_unchanged_content_but_newer_mtime_is_benign():
    result = classify_audit({"/tmp/a.json": "aaa"}, [state("/tmp/a.json", "aaa", 2000)], "", 1000)
    assert result.benign[0].path == "/tmp/a.json"
    assert result.suspicious == ()


def test_changed_content_mentioned_in_ledger_is_acknowledged():
    result = classify_audit(
        {"/tmp/a.json": "old"}, [state("/tmp/a.json", "new", 2000)], "改过 a.json，见流水", 1000
    )
    assert result.suspicious == ()
    assert result.snapshot["/tmp/a.json"] == "new"


def test_changed_content_not_mentioned_alerts_and_keeps_old_fingerprint():
    result = classify_audit(
        {"/tmp/a.json": "old"}, [state("/tmp/a.json", "new", 2000)], "别的记录", 1000
    )
    assert [change.path for change in result.suspicious] == ["/tmp/a.json"]
    assert result.snapshot["/tmp/a.json"] == "old"  # keep alerting until recorded


def test_first_run_alerts_for_unmentioned_file():
    result = classify_audit({}, [state("/tmp/a.json", "new", 2000)], "别的记录", 1000)
    assert result.suspicious
    assert "/tmp/a.json" not in result.snapshot


def test_first_run_acknowledges_mentioned_file():
    result = classify_audit({}, [state("/tmp/a.json", "new", 2000)], "见 a.json", 1000)
    assert result.suspicious == ()
    assert result.snapshot["/tmp/a.json"] == "new"


def test_tolerance_boundary_is_strict():
    ledger_mtime = 1000.0
    exactly = ledger_mtime + AUDIT_MTIME_TOLERANCE
    result = classify_audit(
        {"/tmp/a.json": "aaa"}, [state("/tmp/a.json", "aaa", exactly)], "", ledger_mtime
    )
    assert result.benign == ()


def test_full_path_mention_also_acknowledges():
    result = classify_audit(
        {"/tmp/a.json": "old"},
        [state("/tmp/a.json", "new", 2000)],
        "改了 /tmp/a.json",
        1000,
    )
    assert result.suspicious == ()


def test_ledger_mentions_by_basename_or_path():
    assert ledger_mentions("foo a.json bar", "/tmp/a.json")
    assert ledger_mentions("foo /tmp/a.json bar", "/tmp/a.json")
    assert not ledger_mentions("foo b.json", "/tmp/a.json")


def test_duplicate_real_paths_are_processed_once():
    result = classify_audit(
        {},
        [state("/tmp/a.json", "one", 2000), state("/tmp/a.json", "two", 3000)],
        "",
        1000,
    )
    assert len(result.suspicious) == 1
    # The changed, unmentioned file must NOT enter the snapshot, and the
    # duplicate path is skipped.
    assert result.snapshot == {}


def test_missing_ledger_aborts_without_touching_snapshot():
    # Production prints AUDIT_ERROR and returns before comparing/writing.
    result = classify_audit({"/tmp/a.json": "old"}, [state("/tmp/a.json", "new", 2000)], None, 1000)
    assert result.ledger_missing is True
    assert result.suspicious == () and result.benign == ()
    assert result.snapshot == {"/tmp/a.json": "old"}
