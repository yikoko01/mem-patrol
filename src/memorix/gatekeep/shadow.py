"""Shadow mode + precision bookkeeping (guide §9.1 item 2).

The production gate records calls / review_none / hits and only upgrades after
precision >= 8/10. This kernel keeps the same counters in memory; persistence
is an adapter concern.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ShadowBook:
    upgrade_threshold: float = 0.8
    min_samples: int = 10
    calls: int = 0
    review_none: int = 0
    predicted: int = 0
    hits: int = 0
    first_ts: int = 0
    last_ts: int = 0

    def record_call(self, *, review_none: bool = False, now: int | None = None) -> None:
        current = int(now if now is not None else time.time())
        self.calls += 1
        self.last_ts = current
        if not self.first_ts:
            self.first_ts = current
        if review_none:
            self.review_none += 1

    def record_sample(self, *, predicted: bool, actual: bool) -> None:
        """Only positive predictions enter precision (true-positive rate)."""
        if not predicted:
            return
        self.predicted += 1
        if actual:
            self.hits += 1

    @property
    def precision(self) -> float:
        return (self.hits / self.predicted) if self.predicted else 0.0

    def should_upgrade(self, *, threshold: float | None = None, min_samples: int | None = None) -> bool:
        needed = self.min_samples if min_samples is None else int(min_samples)
        bar = self.upgrade_threshold if threshold is None else float(threshold)
        return self.predicted >= needed and self.precision >= bar

    def snapshot(self) -> dict[str, float | int]:
        return {
            "calls": self.calls,
            "review_none": self.review_none,
            "predicted": self.predicted,
            "hits": self.hits,
            "samples": self.predicted,
            "precision": round(self.precision, 4),
            "hit_rate_ppm": int(self.precision * 1_000_000),
            "first_ts": self.first_ts,
            "last_ts": self.last_ts,
        }
