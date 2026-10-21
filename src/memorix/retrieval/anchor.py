"""Referent anchoring: turn "这个项目" into the entity mentioned just before.

Extracted from ``direct_memory_recall._pick_anchor/_words`` (read-only reference).
Rules kept from production:
* scan the context newest-first, take the first rare noun;
* jieba POS filter (``n*/eng/j``), Chinese priority, strip ``[At:xx]`` residue;
* exclude generic nouns so the anchor never lands on "这个项目".
Without jieba the anchor is empty and the scorer degrades to pure lexical
(no error), exactly as documented in guide §10.4.
"""
from __future__ import annotations

import re

from .tokens import single_line, tokens

ANCHOR_STOP = {
    "我们", "你们", "他们", "这个", "那个", "什么", "因为", "所以", "但是", "如果",
    "就是", "可以", "需要", "一个", "看看", "之前", "现在", "已经", "还是", "没有",
    "不是", "这样", "那样", "真的", "一下", "然后", "而且", "不过", "可能", "应该",
    "知道", "觉得", "自己", "东西", "时候", "今天", "明天", "昨天", "开始", "问题",
    "项目", "内容", "记忆", "记忆库", "系统", "方式", "部分", "阶段", "情况",
    "结果", "原因", "方法", "地方", "功能", "配置", "文件", "数据", "消息",
    "请求", "回复", "记录", "过程", "计划", "方案", "改动", "修改", "版本",
    "沙盒", "盒里", "工作区", "工作台", "dsh",
}

ANCHOR_POS_PREFIX = ("n", "eng", "j")
_AT_RESIDUE_RE = re.compile(r"\[[^\]]{1,24}\]")

_JIEBA = None
_JIEBA_TRIED = False


def jieba_module():
    global _JIEBA, _JIEBA_TRIED
    if not _JIEBA_TRIED:
        _JIEBA_TRIED = True
        try:
            import jieba

            jieba.setLogLevel(60)
            _JIEBA = jieba
        except Exception:  # noqa: BLE001 - optional dependency
            _JIEBA = None
    return _JIEBA


def words(text) -> list[str]:
    """Noun-ish words for anchoring; empty list when jieba is unavailable."""
    module = jieba_module()
    if module is None:
        return []
    try:
        import jieba.posseg as pseg

        cleaned = _AT_RESIDUE_RE.sub(" ", str(text or ""))
        out: list[str] = []
        for word, flag in pseg.cut(cleaned):
            word = str(word or "").strip()
            if len(word) < 2 or word.isspace():
                continue
            if word.isascii() and len(word) < 3:
                continue
            if any(flag.startswith(prefix) for prefix in ANCHOR_POS_PREFIX):
                out.append(word)
        return out
    except Exception:  # noqa: BLE001
        try:
            return [w for w in module.lcut(str(text or "")) if len(w) >= 2 and not w.isspace()]
        except Exception:  # noqa: BLE001
            return []


def anchor_key(anchor: str) -> str:
    """Normalise an anchor for df lookup: ASCII is lower-cased, CJK kept as-is."""
    return anchor.lower() if anchor.isascii() else anchor


def anchor_doc_freq(anchor: str, doc_freq) -> int:
    """Document frequency of an anchor word.

    CJK words longer than 2 chars are not 2-grams themselves, so use the rarest
    of their 2-gram parts (the tokenizer only emits 1/2-grams).
    """
    key = anchor_key(anchor)
    if key in doc_freq:
        return int(doc_freq[key])
    if len(anchor) >= 2 and not anchor.isascii():
        counts = [int(doc_freq.get(gram, 0)) for gram in tokens(anchor)]
        if counts:
            return min(counts)
    return 0


def pick_anchor(context: str, query_tokens: set[str], doc_freq, *, lo: int = 2, hi: int = 60) -> str:
    """First rare noun in the context (newest-first), or ""."""
    messages = [line for line in str(context or "").split("\n") if line.strip()]
    query_norm = single_line(" ".join(str(token) for token in query_tokens), 4000)
    for message in messages:
        if single_line(message, 200) in query_norm:
            continue  # the current message itself
        candidates = [
            word
            for word in words(message)
            if anchor_key(word) not in query_tokens and word not in ANCHOR_STOP
        ]
        # Chinese first; then rarest (lowest document frequency).
        candidates.sort(
            key=lambda word: (1 if word.isascii() else 0, anchor_doc_freq(word, doc_freq))
        )
        for word in candidates:
            count = anchor_doc_freq(word, doc_freq)
            if lo <= count <= hi:
                return word
    return ""
