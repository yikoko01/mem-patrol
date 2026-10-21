"""Bare-promise ("空炮") detector, extracted as a pure reviewer.

Production ships this in shadow mode (record only, never append a flag). The
pure core is :func:`barren_phrase`; the host decides whether to enforce.
Precision first: a question, code block, long body or any concrete content
(number/URL/quote) passes.
"""
from __future__ import annotations

import re
from typing import Any

_PROMISE_RE = re.compile(
    r"(这就去|这就查|这就来|这就找|马上|立刻|在干|正在|搞着|弄着|查一下|找一下"
    r"|稍等|等我|别急|快了|查清了|找到了|搞定了|三个原因|有点眉目)"
)
_CONTENT_RE = re.compile(r"(\d|https?://|《[^》]{1,20}》|「[^」]{2,}」|\"[^\"]{2,}\")")
_STRIP_TTS_RE = re.compile(r"\[\[PCTTS:[^\]]*\]\]")
_PUNCT_RE = re.compile(r"[\s，。！？!?、,.;；:：~～…—\-\(\)（）\[\]【】\"'“”‘’]")
MAX_BARREN_CHARS = 24


def _clean(text: Any) -> str:
    return _STRIP_TTS_RE.sub("", str(text or "")).strip()


def barren_phrase(text: Any) -> str:
    """Return the matched promise word, or "" when the text is not a bare promise."""
    cleaned = _clean(text)
    if not cleaned or len(cleaned) > 120:
        return ""
    if "```" in cleaned:
        return ""
    if "？" in cleaned or "?" in cleaned:
        return ""
    match = _PROMISE_RE.search(cleaned)
    if not match:
        return ""
    core = _PUNCT_RE.sub("", cleaned)
    if len(core) > MAX_BARREN_CHARS:
        return ""
    if _CONTENT_RE.search(cleaned):
        return ""
    return match.group(1)


def flags_for(text: Any, *, reviewed: bool = True) -> list[str]:
    """Review flags for the host; ``reviewed=False`` mirrors the shadow pass-through."""
    if not reviewed:
        return []
    return ["barren_promise"] if barren_phrase(text) else []
