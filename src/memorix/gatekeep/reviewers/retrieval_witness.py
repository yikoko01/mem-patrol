"""Absence-without-retrieval detector, extracted as a pure reviewer.

"说查不到之前，本轮到底查没查" — pure: the host passes the tool names used in
the turn. ``None`` means unknown -> fail open (no flag), matching production.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_ABSENCE_RE = re.compile(
    r"(查不到|没查到|没有查到|搜不到|没搜到|找不到|没有找到|不存在"
    r"|没有记录|没记录|没写过|从未提到|从未出现|从未有过|对不上"
    r"|库里没有|数据库里没有|没有这条记录|没有相关记录)"
)
_EVIDENCE_RE = re.compile(
    r"(我查了|我翻了|我搜了|我检索了|我看了|我读过|翻了一下|查了一遍|搜了一遍"
    r"|翻了台账|翻了记忆|查了库|查了台账|查了记录|搜了|检索过)"
)
RETRIEVAL_PREFIXES = (
    "pc_query", "pc_get_", "pc_manage_", "pc_view_", "pc_send_music",
    "pc_send_pixiv", "pc_find_reaction", "astrbot_execute_shell",
    "astrbot_execute_python", "astrbot_file", "web_search", "fetch_web",
    "search_memes",
)


def absence_claim(text: Any) -> str:
    cleaned = re.sub(r"\[\[PCTTS:[^\]]*\]\]", "", str(text or ""))
    if _EVIDENCE_RE.search(cleaned):
        return ""
    match = _ABSENCE_RE.search(cleaned)
    return match.group(1) if match else ""


def turn_had_retrieval(
    tool_calls: Iterable[str] | None,
    *,
    event_present: bool | None = None,
) -> bool:
    """True when at least one retrieval tool was used.

    ``tool_calls`` semantics: ``None`` = unknown (fail open, True);
    ``[]`` = a turn with no tool calls (False).
    ``event_present=True`` + ``None`` mirrors production's "event exists but has
    no tool-call attribute" case -> False. Adapters must map accordingly.
    """
    if tool_calls is None:
        return not (event_present is True)
    for name in tool_calls:
        if str(name or "").startswith(RETRIEVAL_PREFIXES):
            return True
    return False


def flags_for(
    text: Any,
    tool_calls: Iterable[str] | None = None,
    *,
    event_present: bool | None = None,
) -> list[str]:
    if not absence_claim(text):
        return []
    if turn_had_retrieval(tool_calls, event_present=event_present):
        return []
    return ["absence_without_retrieval"]
