"""Structured metrics for recall / judge / patrol (no third-party deps).

The kernel emits events; aggregation is an adapter concern. This module keeps a
pure in-memory collector plus JSONL helpers, and never reads wall-clock time by
itself (events carry their own timestamps unless the caller passes one).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class MetricEvent:
    kind: str  # judge / recall / patrol
    outcome: str  # sent / dropped / handoff / tool_task / candidate / hit / miss ...
    reason: str = ""
    latency_ms: float | None = None  # None = not measured; 0.0 is a real sample
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    source: str = ""
    ts: float = 0.0
    top_k: int = 0  # recall only
    chars: int = 0  # recall output size
    count: int = 0  # patrol batch size

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping) -> "MetricEvent":
        return cls(
            kind=str(data.get("kind") or ""),
            outcome=str(data.get("outcome") or ""),
            reason=str(data.get("reason") or ""),
            latency_ms=(float(data["latency_ms"]) if data.get("latency_ms") is not None else None),
            tokens_in=int(data.get("tokens_in") or 0),
            tokens_out=int(data.get("tokens_out") or 0),
            cost_usd=float(data.get("cost_usd") or 0.0),
            source=str(data.get("source") or ""),
            ts=float(data.get("ts") or 0.0),
            top_k=int(data.get("top_k") or 0),
            chars=int(data.get("chars") or 0),
            count=int(data.get("count") or 0),
        )


def percentile(values: Iterable[float], p: float) -> float | None:
    """Linear-interpolated percentile; ``None`` when there are no samples."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0,1]")
    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class MetricsCollector:
    """In-memory aggregation; create one per process/run."""

    def __init__(self) -> None:
        self._events: list[MetricEvent] = []

    @property
    def events(self) -> tuple[MetricEvent, ...]:
        return tuple(self._events)

    def record(self, event: MetricEvent) -> None:
        self._events.append(event)

    def record_decision(
        self,
        *,
        outcome: str,
        reason: str = "",
        latency_ms: float | None = None,
        source: str = "",
        ts: float = 0.0,
        kind: str = "judge",
    ) -> None:
        self.record(
            MetricEvent(
                kind=kind,
                outcome=outcome,
                reason=reason,
                latency_ms=(None if latency_ms is None else float(latency_ms)),
                source=source,
                ts=float(ts),
            )
        )

    def record_recall(
        self,
        *,
        hit: bool,
        top_k: int,
        latency_ms: float = 0.0,
        chars: int = 0,
        source: str = "",
        ts: float = 0.0,
    ) -> None:
        outcome = "hit" if hit else "miss"
        self.record(
            MetricEvent(
                kind="recall",
                outcome=outcome,
                latency_ms=float(latency_ms),
                top_k=int(top_k),
                chars=int(chars),
                source=source,
                ts=float(ts),
            )
        )

    def record_patrol(
        self,
        *,
        action: str,
        count: int = 0,
        latency_ms: float = 0.0,
        source: str = "",
        ts: float = 0.0,
    ) -> None:
        self.record(
            MetricEvent(
                kind="patrol",
                outcome=str(action),
                latency_ms=float(latency_ms),
                count=int(count),
                source=source,
                ts=float(ts),
            )
        )

    def snapshot(self) -> dict:
        kinds = Counter(event.kind for event in self._events)
        outcomes = Counter("%s:%s" % (event.kind, event.outcome) for event in self._events)
        reasons = Counter(event.reason for event in self._events if event.reason)
        rejection_reasons = Counter(
            event.reason
            for event in self._events
            if event.reason and event.outcome == "dropped"
        )
        latencies: dict[str, dict[str, float | None]] = {}
        by_kind_latency: dict[str, list[float]] = defaultdict(list)
        for event in self._events:
            if event.latency_ms is not None:
                by_kind_latency[event.kind].append(event.latency_ms)
        for kind, values in by_kind_latency.items():
            latencies[kind] = {
                "p50": percentile(values, 0.5),
                "p90": percentile(values, 0.9),
                "p99": percentile(values, 0.99),
            }
        return {
            "events": len(self._events),
            "by_kind": dict(sorted(kinds.items())),
            "outcomes": dict(sorted(outcomes.items())),
            "reasons": dict(reasons.most_common(20)),
            "rejection_reasons": dict(rejection_reasons.most_common(20)),
            "latency_ms": latencies,
            "tokens_in": sum(event.tokens_in for event in self._events),
            "tokens_out": sum(event.tokens_out for event in self._events),
            "recall_top_k": sum(event.top_k for event in self._events),
            "recall_chars": sum(event.chars for event in self._events),
            "patrol_count": sum(event.count for event in self._events),
            "cost_usd": round(sum(event.cost_usd for event in self._events), 8),
        }


def write_jsonl(path: str | Path, events: Iterable[MetricEvent]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[MetricEvent]:
    events: list[MetricEvent] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            events.append(MetricEvent.from_dict(json.loads(line)))
    return events
