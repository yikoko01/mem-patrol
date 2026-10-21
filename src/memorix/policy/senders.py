"""Real sender labels for the patrol digest.

The production bug this fixes: every ``raw_messages`` row used to be labelled
"用户", so group members (牛杂, 庚金生木, cancev, ...) were all folded into the
owner's voice. Labels are resolved per ``sender_id`` instead.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..models import field_of

__all__ = ["build_sender_name_map", "display_sender"]


def build_sender_name_map(rows: Iterable[Any]) -> dict[str, str]:
    """Map ``sender_id -> best non-empty display name``.

    ``rows`` is any iterable of mappings with ``sender_id`` / ``sender_name``
    (a sqlite3.Row works too). First non-empty name per id wins, which keeps the
    helper deterministic; the production SQL used ``GROUP BY sender_id`` and did
    not define which row's name it returned.
    """
    names: dict[str, str] = {}
    for row in rows:
        sid = str(field_of(row, "sender_id") or "")
        name = str(field_of(row, "sender_name") or "").strip()
        if sid and name and sid not in names:
            names[sid] = name
    return names


def display_sender(row: Any, name_map: Mapping[str, str] | None = None) -> str:
    """Pick a label that distinguishes people in the digest.

    Priority: this row's non-empty name -> same id's name elsewhere ->
    private-chat fallback "用户" -> "用户<id prefix>".
    """
    sid = str(field_of(row, "sender_id") or "")
    name = str(field_of(row, "sender_name") or "").strip()
    if not name and name_map:
        name = str(name_map.get(sid) or "").strip()
    if name:
        return name
    # Private chat has group_id == sender_id; the platform often omits the name.
    if sid and str(field_of(row, "group_id") or "") == sid:
        return "用户"
    return f"用户{sid[:6]}" if sid else "用户"
