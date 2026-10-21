"""Intent TTL: date parsing, classification and the deterministic downgrade."""
from __future__ import annotations

import datetime

import pytest

from memorix.models import IntentReport
from memorix.policy.intents import classify_intents, parse_intent_due, plan_intent_expiry

TODAY = datetime.date(2026, 10, 20)


def intent(memory_id, content, importance=8, memory_type="intent"):
    return {
        "id": memory_id,
        "memory_type": memory_type,
        "importance": importance,
        "content": content,
    }


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("【意图·有效期至 2026-10-25】做 A → B", datetime.date(2026, 10, 25)),
        ("有效期 2026-12-31", datetime.date(2026, 12, 31)),
        ("【意图·有效期至2026-01-02】", datetime.date(2026, 1, 2)),
    ],
)
def test_parse_due_variants(content, expected):
    assert parse_intent_due(content) == expected


@pytest.mark.parametrize(
    "content",
    ["没有日期", "", None, "有效期至 2026-02-30", "有效期至 2026-13-01"],
)
def test_parse_due_invalid(content):
    assert parse_intent_due(content) is None


def test_classify_orders_by_id_and_splits_categories():
    rows = [
        intent(3, "没有有效期"),
        intent(1, "【意图·有效期至 2026-10-19】过期"),
        intent(2, "【意图·有效期至 2026-10-20】今天到期"),
        intent(4, "【意图·有效期至 2026-12-01】非意图类型", memory_type="episodic"),
    ]
    report = classify_intents(rows, TODAY)
    assert [row["id"] for row, _ in report.expired] == [1]
    assert [row["id"] for row, _ in report.pending] == [2]  # due today = still pending
    assert [row["id"] for row in report.badfmt] == [3]


def test_classify_ignores_non_intent_types():
    report = classify_intents([intent(1, "x", memory_type="auto_patrol")], TODAY)
    assert report == IntentReport()


@pytest.mark.parametrize(
    ("importance", "expected"),
    [
        (8, 6),
        (9, 7),
        (10, 8),
        (3, 3),      # floor 3
        (0.5, 3),    # ORM 0-1 float -> *10 -> 5 -> 3
        (1, 8),      # <=1 branch applies, then -2
        ("bad", 5),  # unparseable -> 7.0 -> 5
    ],
)
def test_plan_expiry_arithmetic(importance, expected):
    report = IntentReport(expired=((intent(1, "body", importance), datetime.date(2026, 1, 1)),))
    updates = plan_intent_expiry(report)
    assert len(updates) == 1
    update = updates[0]
    assert update.importance == expected
    assert update.memory_type == "episodic"
    assert update.content == "[意图已过期,2026-01-01] body"
    assert update.due == datetime.date(2026, 1, 1)


def test_plan_expiry_empty_report():
    assert plan_intent_expiry(IntentReport()) == []


def test_plan_expiry_sorted_by_id():
    report = IntentReport(
        expired=(
            (intent(3, "c"), datetime.date(2026, 1, 1)),
            (intent(1, "a"), datetime.date(2026, 1, 1)),
        )
    )
    assert [update.memory_id for update in plan_intent_expiry(report)] == [1, 3]


def test_today_is_required_no_hidden_clock():
    with pytest.raises(TypeError):
        classify_intents([])  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        classify_intents([], None)  # type: ignore[arg-type]
