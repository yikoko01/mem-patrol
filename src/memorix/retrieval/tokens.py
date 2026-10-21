"""Tokenisation shared by the recall scorer (Chinese 2-gram + ASCII words)."""
from __future__ import annotations

import re

_ASCII_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def single_line(value, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def tokens(text) -> set[str]:
    """Chinese 2-gram + ASCII word tokens; no third-party dependency."""
    source = str(text or "").lower()
    if not source:
        return set()
    out: set[str] = set()
    for word in _ASCII_RE.findall(source):
        if len(word) >= 2:
            out.add(word)
    for run in _CJK_RE.findall(source):
        if len(run) == 1:
            out.add(run)
        for index in range(len(run) - 1):
            out.add(run[index : index + 2])
    return out
