"""Finish gate: cursor may only advance after memories and ledger really exist.

Faithful extraction of ``memory_patrol._verify_writes`` (the "漏账不可作废"
contract). Error strings are kept **verbatim** so operators see the same messages
and the M1 CLI can print them unchanged.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..models import as_int, field_of
from .timeparse import parse_ts

__all__ = ["verify_finish"]


def _candidate_keys(memory_id: Any):
    """Keys to try, mirroring SQLite numeric affinity (``"1.0"`` matches id 1)."""
    yield memory_id
    try:
        yield int(memory_id)
    except (TypeError, ValueError):
        pass
    try:
        numeric = float(memory_id)
    except (TypeError, ValueError):
        return
    # SQLite numeric affinity turns "1.0" into 1 but "1.9" into 1.9 (no match).
    if numeric.is_integer():
        yield int(numeric)


def _lookup(memories_by_id: Mapping[Any, Any], memory_id: Any) -> Any:
    for key in _candidate_keys(memory_id):
        try:
            if key in memories_by_id:
                return memories_by_id[key]
        except TypeError:  # unhashable key, keep trying
            continue
    return None


def verify_finish(
    mem_ids: Iterable[Any] | None,
    ledger_mark: str | None,
    *,
    memories_by_id: Mapping[Any, Any],
    ledger_text: str | None,
    prev_finish_ts: int = 0,
    ledger_path: str = "change_history.md",
    parse_ts_fn=parse_ts,
) -> list[str]:
    """Return the gate errors; an empty list means the finish may proceed.

    ``mem_ids`` semantics follow production:
    * ``None`` -> refused (missing argument);
    * ``["none"]`` -> explicitly no memories this round;
    * otherwise each id must exist and be newer than the previous finish.
    ``ledger_text is None`` means the ledger file does not exist.
    """
    errors: list[str] = []

    # Materialise once: callers may pass a list, tuple or generator.
    if mem_ids is not None:
        mem_ids = list(mem_ids)

    if mem_ids is None:
        errors.append("缺 --mem-ids（本轮写入的记忆 id，逗号分隔；确实无收获写 --mem-ids=none）")
    elif mem_ids != ["none"]:
        if not mem_ids:
            errors.append("--mem-ids 为空")
        else:
            previous = int(prev_finish_ts or 0)
            for memory_id in mem_ids:
                row = _lookup(memories_by_id, memory_id)
                if row is None:
                    errors.append("记忆 #%s 不存在——先落库，再来收尾" % memory_id)
                    continue
                if previous and parse_ts_fn(field_of(row, "created_at")) <= previous:
                    errors.append("记忆 #%s 写入时间早于上轮收尾，不像是本轮新写的" % memory_id)

    if ledger_mark is None:
        errors.append("缺 --ledger（本轮台账条目的标题片段；没动配置写 --ledger=none）")
    elif ledger_mark != "none":
        if ledger_text is None:
            errors.append("台账文件不存在：%s" % ledger_path)
        elif ledger_mark not in ledger_text:
            errors.append("台账里找不到「%s」——先记账，再来收尾" % ledger_mark)

    return errors
