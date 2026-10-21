"""Recent private context (handoff rule: private when group_id == sender_id)."""
from __future__ import annotations

from pathlib import Path

from ..store import SQLiteStore
from .tokens import single_line


def recent_private_context(
    db_path: str | Path,
    user_id: str,
    *,
    limit: int = 4,
    schema=None,
    max_chars: int = 200,
    as_of_ts: int | None = None,
) -> str:
    """Newest-first lines of the user's private messages, for anchor extraction.

    Group messages are excluded by the handoff rule; using the whole raw table
    would put group members' words into the user's "original words" anchor.
    """
    with SQLiteStore(db_path, readonly=True, schema=schema) as store:
        rows = store.recent_private_messages(user_id, limit, before_ts=as_of_ts)
    lines: list[str] = []
    for row in rows:
        text = single_line(row["message"], max_chars)
        if text:
            lines.append(text)
    return "\n".join(lines)
