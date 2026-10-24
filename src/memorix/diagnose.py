"""Read-only diagnosis: turn a memory table + optional state/audit into findings.

This is the "diagnose" half of the M1 diagnose/repair loop. It never writes.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import AuditResult, MemoryRecord
from .policy.consolidation import RECENT_EPISODIC_WINDOW, recent_episodic
from .policy.decay import plan_decay
from .policy.intents import classify_intents
from .policy.orphan import ORPHAN_MEMORY_TYPES, detect_orphans
from .state import PatrolState

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "INFO": 2, "LOW": 3}


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    evidence: str = ""


@dataclass
class Diagnosis:
    total: int
    distribution: dict[str, int]
    data_quality: dict[str, int]
    orphans: list = field(default_factory=list)
    decay: list = field(default_factory=list)
    intents: Any = None
    recent_episodic: list = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    audit: AuditResult | None = None
    state: PatrolState | None = None

    def has_high(self) -> bool:
        return any(finding.severity == "HIGH" for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "distribution": dict(self.distribution),
            "data_quality": dict(self.data_quality),
            "orphans": [orphan.__dict__ for orphan in self.orphans],
            "decay": [action.__dict__ for action in self.decay],
            "intents": {
                "pending": len(self.intents.pending) if self.intents else 0,
                "expired": len(self.intents.expired) if self.intents else 0,
                "badfmt": len(self.intents.badfmt) if self.intents else 0,
            },
            "recent_episodic": [memory.id for memory in self.recent_episodic],
            "findings": [finding.__dict__ for finding in self.findings],
            "audit": None
            if self.audit is None
            else {
                "suspicious": [change.path for change in self.audit.suspicious],
                "benign": [change.path for change in self.audit.benign],
                "ledger_missing": self.audit.ledger_missing,
            },
            "state": None if self.state is None else self.state.to_dict(),
        }


def measure_data_quality(memories: Iterable[MemoryRecord]) -> dict[str, int]:
    """Mirror the SQL ``typeof`` checks the production ``_data_quality`` does."""
    total = non_integer_importance = non_ms_created_at = 0
    for memory in memories:
        total += 1
        if not isinstance(memory.importance, int):
            non_integer_importance += 1
        if not (isinstance(memory.created_at, int) and memory.created_at > 10**11):
            non_ms_created_at += 1
    return {
        "total": total,
        "non_integer_importance": non_integer_importance,
        "non_ms_created_at": non_ms_created_at,
    }


def build_diagnosis(
    memories: Iterable[MemoryRecord],
    *,
    state: PatrolState | None = None,
    audit: AuditResult | None = None,
    now: int | None = None,
    user_max: int | None = None,
    bot_max: int | None = None,
) -> Diagnosis:
    memories = list(memories)
    now = int(now) if now is not None else int(_dt.datetime.now().timestamp())
    distribution: dict[str, int] = {}
    for memory in memories:
        distribution[memory.memory_type] = distribution.get(memory.memory_type, 0) + 1

    quality = measure_data_quality(memories)
    last_finish = state.last_finish_ts if state is not None else 0
    orphans = detect_orphans(memories, last_finish, ORPHAN_MEMORY_TYPES)
    decay = plan_decay(memories, now)
    intents = classify_intents(
        [memory for memory in memories], _dt.date.fromtimestamp(now)
    )
    recent = recent_episodic(memories, RECENT_EPISODIC_WINDOW)

    findings: list[Finding] = []

    def add(severity: str, code: str, message: str, evidence: str = "") -> None:
        findings.append(Finding(severity, code, message, evidence))

    if quality["total"] == 0:
        add("HIGH", "empty-memories", "memories 表为空，巡检/衰减/画像都无从谈起")
    if quality["non_integer_importance"]:
        add(
            "HIGH",
            "importance-type",
            "importance 列混入非整数，`>=9`/`<=3` 阈值会静默失效",
            "rows=%d" % quality["non_integer_importance"],
        )
    if quality["non_ms_created_at"]:
        add(
            "HIGH",
            "created-at-encoding",
            "created_at 混有秒/ISO/文本口径，排序与孤儿判定会偏",
            "rows=%d" % quality["non_ms_created_at"],
        )
    if orphans:
        add(
            "HIGH",
            "orphan-batch",
            "存在已写入但游标未推进的孤儿批次",
            "ids=%s" % ",".join(str(orphan.memory_id) for orphan in orphans[:10]),
        )
    if decay:
        add(
            "INFO",
            "decay-pending",
            "有可衰减记忆（SOP：>30 天且 importance<=3）",
            "count=%d" % len(decay),
        )
    if intents.badfmt:
        add(
            "MEDIUM",
            "intent-badfmt",
            "意图条目缺可解析的有效期，过期降级不会触发",
            "ids=%s" % ",".join(str(memory.id) for memory in intents.badfmt[:10]),
        )
    if intents.expired:
        add(
            "INFO",
            "intent-expired",
            "有已过期但尚未降级的意图",
            "count=%d" % len(intents.expired),
        )
    if audit is not None:
        if audit.ledger_missing:
            add("HIGH", "audit-ledger-missing", "审计台账文件缺失，无法判断留痕")
        if audit.suspicious:
            add(
                "HIGH",
                "audit-suspicious",
                "有配置改动未在台账留痕",
                "files=%d" % len(audit.suspicious),
            )
        if audit.benign:
            add(
                "INFO",
                "audit-benign",
                "mtime 刷新但内容未变（良性）",
                "files=%d" % len(audit.benign),
            )
    if state is None:
        add("INFO", "no-state", "没有巡检状态文件（首次运行或路径不对）")
    else:
        if user_max is not None and state.last_user_msg_id > user_max:
            add(
                "HIGH",
                "cursor-ahead-user",
                "状态游标大于 raw_messages 最大 id，库/状态不匹配",
                "%d > %d" % (state.last_user_msg_id, user_max),
            )
        if bot_max is not None and state.last_bot_msg_id > bot_max:
            add(
                "HIGH",
                "cursor-ahead-bot",
                "状态游标大于 bot_messages 最大 id，库/状态不匹配",
                "%d > %d" % (state.last_bot_msg_id, bot_max),
            )

    findings.sort(key=lambda finding: (SEVERITY_ORDER.get(finding.severity, 9), finding.code))
    return Diagnosis(
        total=quality["total"],
        distribution=distribution,
        data_quality=quality,
        orphans=orphans,
        decay=decay,
        intents=intents,
        recent_episodic=recent,
        findings=findings,
        audit=audit,
        state=state,
    )


def format_diagnosis(diagnosis: Diagnosis) -> str:
    lines = ["MEMORIX_DIAGNOSIS", "total=%d" % diagnosis.total]
    for memory_type, count in sorted(diagnosis.distribution.items()):
        lines.append("type.%s=%d" % (memory_type, count))
    for key, value in diagnosis.data_quality.items():
        lines.append("quality.%s=%d" % (key, value))
    lines.append("orphan=%d" % len(diagnosis.orphans))
    lines.append("decay_pending=%d" % len(diagnosis.decay))
    lines.append("intent_pending=%d" % len(diagnosis.intents.pending))
    lines.append("intent_expired=%d" % len(diagnosis.intents.expired))
    lines.append("intent_badfmt=%d" % len(diagnosis.intents.badfmt))
    lines.append("recent_episodic=%d" % len(diagnosis.recent_episodic))
    if diagnosis.audit is not None:
        lines.append("audit_suspicious=%d" % len(diagnosis.audit.suspicious))
        lines.append("audit_benign=%d" % len(diagnosis.audit.benign))
    for finding in diagnosis.findings:
        lines.append(
            "finding.%s.%s=%s%s"
            % (
                finding.severity,
                finding.code,
                finding.message,
                (" [%s]" % finding.evidence) if finding.evidence else "",
            )
        )
    if not diagnosis.findings:
        lines.append("finding=OK")
    return "\n".join(lines)
