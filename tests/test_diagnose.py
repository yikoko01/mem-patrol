"""Read-only diagnosis: data-quality traps, orphans, intents, audit drift."""
from __future__ import annotations

from memorix.diagnose import build_diagnosis, format_diagnosis, measure_data_quality
from memorix.models import AuditResult, FileChange, MemoryRecord
from memorix.state import PatrolState

NOW = 1_800_000_000
DAY = 86_400


def mem(memory_id, memory_type="auto_patrol", importance=7, created_at=NOW, content=""):
    return MemoryRecord(
        id=memory_id,
        memory_type=memory_type,
        importance=importance,
        created_at=created_at,
        content=content,
    )


def codes(diagnosis):
    return [finding.code for finding in diagnosis.findings]


def test_distribution_and_totals():
    diagnosis = build_diagnosis(
        [mem(1), mem(2, "episodic"), mem(3, "episodic")], now=NOW
    )
    assert diagnosis.total == 3
    assert diagnosis.distribution == {"auto_patrol": 1, "episodic": 2}


def test_empty_memories_is_high():
    diagnosis = build_diagnosis([], now=NOW)
    assert "empty-memories" in codes(diagnosis)
    assert diagnosis.has_high()


def test_text_importance_is_high():
    diagnosis = build_diagnosis([mem(1, importance="system")], now=NOW)
    assert "importance-type" in codes(diagnosis)
    assert diagnosis.has_high()


def test_seconds_created_at_is_high():
    diagnosis = build_diagnosis([mem(1, created_at=NOW)], now=NOW)  # seconds, not ms
    finding = next(item for item in diagnosis.findings if item.code == "created-at-encoding")
    assert finding.severity == "HIGH"


def test_measure_data_quality_matches_typeof_semantics():
    quality = measure_data_quality(
        [
            mem(1, created_at=NOW * 1000),
            mem(2, importance=7.5, created_at=NOW * 1000),
            mem(3, created_at=NOW),
        ]
    )
    assert quality == {
        "total": 3,
        "non_integer_importance": 1,
        "non_ms_created_at": 1,
    }


def test_orphan_batch_is_high():
    state = PatrolState(last_finish_ts=NOW - 1000)
    diagnosis = build_diagnosis(
        [mem(1, "auto_patrol"), mem(2, "auto_patrol", created_at=NOW - 5000)],
        state=state,
        now=NOW,
    )
    assert "orphan-batch" in codes(diagnosis)
    assert diagnosis.has_high()


def test_cursor_ahead_is_high():
    state = PatrolState(last_user_msg_id=99, last_bot_msg_id=99)
    diagnosis = build_diagnosis(
        [mem(1)], state=state, now=NOW, user_max=4, bot_max=2
    )
    assert "cursor-ahead-user" in codes(diagnosis)
    assert "cursor-ahead-bot" in codes(diagnosis)


def test_intent_badfmt_medium_and_expired_info():
    rows = [
        mem(1, "intent", 8, NOW, "没有日期"),
        mem(2, "intent", 8, NOW, "【意图·有效期至 2020-01-01】过期"),
    ]
    diagnosis = build_diagnosis(rows, now=NOW)
    assert "intent-badfmt" in codes(diagnosis)
    assert "intent-expired" in codes(diagnosis)


def test_decay_pending_is_info():
    diagnosis = build_diagnosis(
        [mem(1, "episodic", importance=2, created_at=(NOW - 31 * DAY) * 1000)],
        now=NOW,
    )
    assert "decay-pending" in codes(diagnosis)
    assert diagnosis.decay[0].memory_id == 1


def test_audit_untrusted_and_benign():
    audit = AuditResult(
        suspicious=(FileChange("/tmp/a.json", 2000, "x"),),
        benign=(FileChange("/tmp/b.json", 2000, "y"),),
    )
    diagnosis = build_diagnosis([mem(1)], audit=audit, now=NOW)
    assert "audit-suspicious" in codes(diagnosis)
    assert "audit-benign" in codes(diagnosis)
    assert diagnosis.has_high()
    missing = build_diagnosis([mem(1)], audit=AuditResult(ledger_missing=True), now=NOW)
    assert "audit-ledger-missing" in codes(missing)


def test_no_state_is_info_only():
    diagnosis = build_diagnosis([mem(1, created_at=NOW * 1000)], now=NOW)
    assert "no-state" in codes(diagnosis)
    assert not diagnosis.has_high()


def test_clean_dataset_has_no_findings():
    diagnosis = build_diagnosis(
        [mem(1, importance=7, created_at=(NOW - 2000) * 1000)],
        state=PatrolState(last_finish_ts=NOW - 1000),
        now=NOW,
    )
    assert diagnosis.findings == []
    assert "finding=OK" in format_diagnosis(diagnosis)


def test_format_and_to_dict():
    diagnosis = build_diagnosis(
        [mem(1, importance="system")], state=None, now=NOW
    )
    text = format_diagnosis(diagnosis)
    assert "MEMORIX_DIAGNOSIS" in text
    assert "finding.HIGH.importance-type" in text
    data = diagnosis.to_dict()
    assert data["total"] == 1
    assert data["distribution"] == {"auto_patrol": 1}
    assert data["findings"]


def test_created_at_encoding_high_invariant():
    # A bad created_at invalidates sorting/decay conclusions, so it is HIGH.
    diagnosis = build_diagnosis([mem(1, created_at=NOW)], now=NOW)
    findings = {finding.code: finding for finding in diagnosis.findings}
    assert findings["created-at-encoding"].severity == "HIGH"
