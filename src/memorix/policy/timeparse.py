"""Timestamp normalisation.

Production data mixes three encodings in the same column:
epoch milliseconds (the majority), epoch seconds, and ISO-8601 text.
This is a faithful extraction of ``memory_patrol._parse_ts``.
"""
from __future__ import annotations

import datetime
import math
from typing import Any

__all__ = ["parse_ts"]

_MS_THRESHOLD = 1e11


def parse_ts(value: Any) -> int:
    """Return an epoch-seconds int, or 0 when the value cannot be understood.

    Kept deliberately lenient around the three historical encodings; callers
    depend on this leniency (orphan detection runs over dirty legacy rows).
    """
    if value is None:
        return 0
    if isinstance(value, str):
        try:
            return int(datetime.datetime.fromisoformat(value.replace("Z", "")).timestamp())
        except Exception:  # noqa: BLE001 - historical data, best effort
            try:
                value = float(value)
            except Exception:  # noqa: BLE001
                return 0
    # Non-numeric / non-finite inputs must not crash the patrol (dirty legacy rows).
    if isinstance(value, bool):
        value = int(value)
    if not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    if value > _MS_THRESHOLD:
        value = value / 1000
    return int(value)
