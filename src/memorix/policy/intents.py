"""Intent TTL (the L7 intent layer).

Production ``cmd_intents``:
* an intent must carry ``【意图·有效期至 YYYY-MM-DD】`` in its content;
* expired intents are downgraded to ``episodic``, importance -2 (floor 3) and the
  content is prefixed with ``[意图已过期,<date>] ``;
* rows without a parseable date are reported as BADFMT and left untouched.

Extracted as classification + deterministic update planning. The DB write is M1.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Iterable

from ..models import IntentReport, IntentUpdate, as_int, field_of

__all__ = ["INTENT_DATE_RE", "parse_intent_due", "classify_intents", "plan_intent_expiry"]

# Same regex as production (memory_patrol.py, read-only reference).
INTENT_DATE_RE = re.compile(r"有效期\s*[至到:：]?\s*(\d{4}-\d{2}-\d{2})")


def parse_intent_due(content: str | None) -> datetime.date | None:
    """Extract the due date from an intent's content, or None if absent/invalid."""
    match = INTENT_DATE_RE.search(content or "")
    if not match:
        return None
    try:
        return datetime.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def classify_intents(
    memories: Iterable[Any],
    today: datetime.date,
) -> IntentReport:
    """Split intent rows into pending / expired / bad-format, ordered by id.

    ``today`` is mandatory so the kernel has no hidden clock; the M1 adapter
    passes ``datetime.date.today()``.
    """
    if today is None:
        raise ValueError("today is required (inject the clock at the adapter layer)")
    rows = [
        row
        for row in memories
        if str(field_of(row, "memory_type") or "") == "intent"
    ]
    rows.sort(key=lambda row: as_int(field_of(row, "id")))

    pending: list[tuple[Any, datetime.date]] = []
    expired: list[tuple[Any, datetime.date]] = []
    badfmt: list[Any] = []
    for row in rows:
        due = parse_intent_due(str(field_of(row, "content") or ""))
        if due is None:
            badfmt.append(row)
        elif due < today:
            expired.append((row, due))
        else:
            pending.append((row, due))
    return IntentReport(
        pending=tuple(pending),
        expired=tuple(expired),
        badfmt=tuple(badfmt),
    )


def plan_intent_expiry(report: IntentReport) -> list[IntentUpdate]:
    """Plan the production downgrade for every expired intent in ``report``.

    The ``importance <= 1 -> *10`` branch exists because the ORM historically
    wrote 0-1 floats into the same column; it is preserved verbatim.
    """
    updates: list[IntentUpdate] = []
    for row, due in report.expired:
        raw_importance = field_of(row, "importance", 0)
        try:
            importance = float(raw_importance or 0)
        except (TypeError, ValueError):
            importance = 7.0
        if importance <= 1.0:
            importance *= 10.0
        new_importance = max(3, int(round(importance)) - 2)
        content = str(field_of(row, "content") or "")
        updates.append(
            IntentUpdate(
                memory_id=as_int(field_of(row, "id")),
                memory_type="episodic",
                importance=new_importance,
                content="[意图已过期," + due.isoformat() + "] " + content,
                due=due,
            )
        )
    updates.sort(key=lambda update: update.memory_id)
    return updates
