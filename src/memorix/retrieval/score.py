"""Lexical recall scoring: anchor + position/density + idf-weighted overlap.

Extracted from ``direct_memory_recall.recall`` (guide §10.2) with the two fixes
the six replay cases require:

1. **query / instruction separation** — only the user's own words are matched;
   an ``instruction`` string is accepted for provenance but explicitly ignored
   (guide §10.3 case 6: instruction words used to pull contracts to the top).
2. **no-anchor coverage floor** — without an anchor (context), a row must cover
   at least ``MIN_COVERAGE_WITHOUT_ANCHOR`` of the query's idf weight; this is
   what stops "今天天气不错" from injecting a contract that merely contains
   "不错" (guide §10.3 case 5).

Known limits (guide §10.4): heuristic; one anchor only; no semantics; the real
fix is an embedding-backed ``vector`` provider behind the same API.
"""
from __future__ import annotations

import datetime
import math
import time
from dataclasses import dataclass
from typing import Iterable

from .anchor import anchor_key, pick_anchor
from .store import RetrievalRow, doc_freq as build_doc_freq
from .tokens import single_line, tokens

MIN_COVERAGE_WITHOUT_ANCHOR = 0.25

# Generic query tokens (pronouns / demonstratives / meta nouns). They carry no
# topical evidence and otherwise let a memory that *mentions* the question's
# generic words outrank the memory that actually answers it ("这个项目...").
_QUERY_STOP = {
    "我们", "你们", "他们", "这个", "那个", "项目", "内容", "什么", "因为",
    "就是", "可以", "需要", "一个", "之前", "现在", "已经", "还是", "没有",
    "不是", "这样", "那样", "真的", "一下", "然后", "而且", "不过", "可能",
    "应该", "知道", "觉得", "自己", "东西", "时候", "今天", "明天", "昨天",
}

_TYPE_LABEL = {
    "contract": "契约",
    "user_preference": "偏好",
    "learning_gap": "教训",
    "episodic": "情景",
    "auto_patrol": "语义",
    "semantic": "语义",
    "progress": "进展",
    "system_change": "系统改",
    "manual_remember": "手记",
    "manual": "手记",
    "profile": "画像",
    "intent": "意图",
    "archived": "归档",
}
_TYPE_BOOST = {"contract": 0.25, "user_preference": 0.2, "learning_gap": 0.12, "intent": 0.15}


def _anchor_match_tokens(anchor: str) -> set[str]:
    if anchor.isascii():
        return {anchor_key(anchor)}
    if len(anchor) <= 2:
        return {anchor}
    return tokens(anchor)


def _anchor_in_row(anchor: str, row: RetrievalRow) -> bool:
    return _anchor_match_tokens(anchor) <= row.tokens


@dataclass(frozen=True)
class ScoredMemory:
    row: RetrievalRow
    score: float
    coverage: float
    anchor_hit: bool


def _date_short(created_at: int) -> str:
    try:
        return datetime.datetime.fromtimestamp(int(created_at)).strftime("%m-%d")
    except (OSError, OverflowError, ValueError):
        return ""


def _idf(doc_freq: dict[str, int], total: int, token: str) -> float:
    return math.log((total + 1.0) / (doc_freq.get(token, 0) + 1.0)) + 0.1


def rank(
    query: str,
    *,
    rows: Iterable[RetrievalRow],
    doc_freq: dict[str, int] | None = None,
    context: str = "",
    group_id: str = "",
    user_id: str = "",
    top_k: int = 5,
    instruction: str = "",
    min_coverage_without_anchor: float = MIN_COVERAGE_WITHOUT_ANCHOR,
) -> list[ScoredMemory]:
    """Rank rows for one query. ``instruction`` is accepted but never matched."""
    del instruction  # explicit: instruction text must not influence ranking
    rows = list(rows)
    query = single_line(query, 1200)
    if not query or not rows:
        return []
    query_tokens = tokens(query)
    if not query_tokens:
        return []
    # Score only topical tokens; fall back to all tokens for ultra-short queries.
    scoring_tokens = query_tokens - _QUERY_STOP or query_tokens
    context_tokens = tokens(context) if context else set()
    match_tokens = scoring_tokens | context_tokens
    doc_freq = doc_freq if doc_freq is not None else build_doc_freq(rows)
    total = len(rows)
    query_weight = sum(_idf(doc_freq, total, token) for token in scoring_tokens) or 1.0

    anchor = pick_anchor(context, query_tokens, doc_freq) if context else ""
    anchored = [row for row in rows if anchor and _anchor_in_row(anchor, row)]
    limit = max(1, int(top_k or 5))
    use_anchor = bool(anchor) and len(anchored) >= limit
    pool = anchored if use_anchor else rows

    scored: list[ScoredMemory] = []
    for row in pool:
        if user_id and row.user_id and row.user_id != user_id:
            continue  # never cross users
        matched = row.tokens & match_tokens
        if not matched:
            continue
        matched_query = row.tokens & scoring_tokens
        matched_context_only = matched - matched_query
        coverage = sum(_idf(doc_freq, total, token) for token in matched_query) / query_weight
        anchor_hit = bool(anchor) and _anchor_in_row(anchor, row)
        if use_anchor and not anchor_hit:
            continue
        # Floor uses the token *count* ratio (robust on tiny/foreign corpora);
        # the score still uses idf-weighted coverage below.
        token_coverage = len(matched_query) / max(1, len(query_tokens))
        if not anchor_hit and token_coverage < min_coverage_without_anchor:
            continue
        # Contracts/preferences have a dedicated injection surface. Lexical
        # recall must never pull them in without an anchor hit, otherwise
        # "今天天气不错"/instruction words surface unrelated contracts
        # (guide §10.3 cases 5 and 6).
        if row.memory_type in {"contract", "user_preference"} and not anchor_hit:
            continue

        # Query evidence outranks context-only evidence: the anchor admits a
        # row to the pool, but the user's own words decide the order.
        matched_weight = sum(_idf(doc_freq, total, token) for token in matched_query)
        matched_weight += 0.05 * sum(
            _idf(doc_freq, total, token) for token in matched_context_only
        )
        score = (
            matched_weight * 0.30
            + coverage * 1.20
            + min(max(row.importance, 0), 10) / 10.0 * 0.50
            + _TYPE_BOOST.get(row.memory_type, 0.0)
        )
        if anchor_hit:
            content = row.content
            if content.startswith(anchor) and ("项目=" in content[:24] or "项目＝" in content[:24]):
                score += 0.4  # canonical "X项目=..." memory beats version/incident notes
            haystack = content.lower() if anchor.isascii() else content
            needle = anchor_key(anchor)
            length = max(1, len(content))
            hits = haystack.count(needle)
            position = 1.0 / (1.0 + max(0, haystack.find(needle)) / 20.0)
            density = min(1.0, (hits / (length / 100.0)) / 2.0)
            score += position * 1.2 + density * 0.3
        if group_id and row.group_id == group_id:
            score += 0.1
        if user_id and row.user_id == user_id:
            score += 0.05
        scored.append(ScoredMemory(row=row, score=score, coverage=coverage, anchor_hit=anchor_hit))

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def format_scored(
    scored: Iterable[ScoredMemory], *, max_chars: int = 900, limit: int | None = None
) -> str:
    budget = max(240, min(1800, int(max_chars or 900)))
    lines: list[str] = []
    total = 0
    for index, item in enumerate(scored):
        if limit is not None and index >= int(limit):
            break
        row = item.row
        label = _TYPE_LABEL.get(row.memory_type, row.memory_type or "记忆")
        date = _date_short(row.created_at)
        meta = "[%s·%s·%s]" % (label, row.importance, date) if date else "[%s·%s]" % (label, row.importance)
        line = "- %s %s" % (meta, single_line(row.content, 160))
        if total + len(line) > budget:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def recall_scored(
    query: str,
    *,
    rows: Iterable[RetrievalRow],
    doc_freq: dict[str, int] | None = None,
    context: str = "",
    group_id: str = "",
    user_id: str = "",
    top_k: int = 5,
    instruction: str = "",
) -> list[ScoredMemory]:
    return rank(
        query,
        rows=rows,
        doc_freq=doc_freq,
        context=context,
        group_id=group_id,
        user_id=user_id,
        top_k=top_k,
        instruction=instruction,
    )


def recall(
    query: str,
    *,
    rows: Iterable[RetrievalRow],
    doc_freq: dict[str, int] | None = None,
    context: str = "",
    group_id: str = "",
    user_id: str = "",
    top_k: int = 5,
    max_chars: int = 900,
    instruction: str = "",
    metrics: Any = None,
    source: str = "",
) -> str:
    """Return the formatted top-k memory block, or "" when nothing is relevant.

    ``metrics`` (optional) receives one recall event (hit/miss, top_k, latency, chars).
    """
    started = time.perf_counter()
    scored = recall_scored(
        query,
        rows=rows,
        doc_freq=doc_freq,
        context=context,
        group_id=group_id,
        user_id=user_id,
        top_k=top_k,
        instruction=instruction,
    )
    text = format_scored(scored, max_chars=max_chars, limit=top_k)
    if metrics is not None:
        metrics.record_recall(
            hit=bool(text),
            top_k=min(int(top_k), len(scored)),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            chars=len(text),
            source=source or group_id,
        )
    return text
