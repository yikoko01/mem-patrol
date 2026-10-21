"""Deterministic gates extracted from ``_group_interjection_allowed`` and friends.

Each gate is pure with respect to its inputs (a ``Context``); the only stateful
one is :class:`ConsultThrottleGate`, whose per-group timestamp map is explicitly
injected. Soft gates return a ``weight`` instead of silently vetoing.
"""
from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .models import Context, GateResult

# ── helpers ──────────────────────────────────────────────────────────
def _cfg(ctx: Context, key: str, default: Any) -> Any:
    value = ctx.config.get(key, default)
    return default if value is None else value


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _day_key(timestamp: float) -> str:
    return datetime.datetime.fromtimestamp(float(timestamp)).strftime("%Y-%m-%d")


def _single_line(value: Any, limit: int = 200) -> str:
    return " ".join(str(value or "").split())[:limit]


def default_topic_signature(text: Any) -> str:
    """Stable, host-free topic signature (production's signature is injected)."""
    return hashlib.sha1(_single_line(text, 80).encode("utf-8")).hexdigest()[:16]


def stable_roll(*parts: Any) -> float:
    """Deterministic 0..1 roll keyed to the trigger (production's sha256 dice)."""
    seed = "|".join(str(part) for part in parts)
    digest = int(hashlib.sha256(seed.encode("utf-8", "ignore")).hexdigest()[:12], 16)
    return (digest % 100000) / 100000.0


# ── budget ───────────────────────────────────────────────────────────
def relative_budget(
    group: Mapping[str, Any],
    *,
    window: int = 30,
    ceiling: float = 0.35,
    floor: float = 0.15,
    head_ratio: float = 0.9,
) -> float:
    """Bot traffic share vs the busiest human's share; 1.0 = plenty of room.

    ``group["recent_messages"]`` is assumed already filtered by the adapter
    (production calls ``_filtered_group_recent_messages`` first).
    """
    recent = group.get("recent_messages") if isinstance(group.get("recent_messages"), list) else []
    bot_replies = (
        group.get("recent_bot_replies") if isinstance(group.get("recent_bot_replies"), list) else []
    )
    stream: list[tuple[float, str]] = []
    for item in recent:
        if isinstance(item, dict):
            stream.append((_as_float(item.get("ts"), 0.0), "human"))
    for item in bot_replies:
        if isinstance(item, dict):
            stream.append((_as_float(item.get("ts"), 0.0), "bot"))
    stream = [entry for entry in stream if entry[0] > 0]
    stream.sort(key=lambda entry: entry[0])
    if not stream:
        return 1.0
    effective_window = int(window) if window else 30  # production: int(window or 30)
    tail = stream[-max(5, effective_window) :]
    bot_share = sum(1 for _, kind in tail if kind == "bot") / len(tail)
    members = group.get("members") if isinstance(group.get("members"), dict) else {}
    counts = [
        max(0, _as_int(member.get("count"), 0))
        for member in members.values()
        if isinstance(member, dict)
    ]
    total = sum(counts)
    peak_share = (max(counts) / total) if total > 0 else 0.0
    effective_ceiling = min(ceiling, max(floor, head_ratio * peak_share))
    if effective_ceiling <= 0:
        return 1.0
    return max(0.0, min(1.0, (effective_ceiling - bot_share) / effective_ceiling))


# ── gates ────────────────────────────────────────────────────────────
class Gate:
    name = "gate"

    def check(self, ctx: Context) -> GateResult:  # pragma: no cover - interface
        raise NotImplementedError


class EnabledGate(Gate):
    name = "enabled"

    def check(self, ctx: Context) -> GateResult:
        if not bool(_cfg(ctx, "enable_group_interjection", False)):
            return GateResult(False, "群聊主动插话未开启")
        return GateResult(True)


class ExplicitDirectionGate(Gate):
    """Explicit @/reply/quote is a hard veto; inferred direction is only a weight."""

    name = "explicit_direction"
    explicit_triggers = frozenset({"at_bot", "reply_bot", "mention_bot_name", "explicit_at", "explicit_reply"})

    def check(self, ctx: Context) -> GateResult:
        if ctx.directed or ctx.addressed_to_bot or ctx.scene_trigger in self.explicit_triggers:
            return GateResult(True)  # explicitly addressed to the bot -> judge decides
        if re.search(r"^\s*(?:@|回复|引用)", ctx.text):
            return GateResult(False, "当前消息有明确对话对象")
        weight = 1.0
        if ctx.talking_to not in {"", "group", "bot"}:
            source = ctx.talking_to_source
            if ctx.talking_to_confidence >= 0.7:
                if source in self.explicit_triggers:
                    return GateResult(False, "当前更像群友之间的一对一对话")
                weight = 0.25
            elif ctx.talking_to_confidence >= 0.55:
                weight = 0.4
        return GateResult(True, weight=weight)


class DoNotInterruptGate(Gate):
    name = "do_not_interrupt"

    def check(self, ctx: Context) -> GateResult:
        if re.search(r"(别插|别接|别吵|别回|闭嘴|别打断)", ctx.text):
            return GateResult(False, "群友表达了不希望被打断")
        return GateResult(True)


class DailyCapGate(Gate):
    name = "daily_cap"

    def check(self, ctx: Context) -> GateResult:
        max_daily = _as_int(_cfg(ctx, "group_interject_max_daily", 0), 0)
        if max_daily <= 0:
            return GateResult(False, "群聊主动插话上限为 0")
        group = ctx.group
        today = _day_key(ctx.timestamp)
        stored_day = str(group.get("interject_day") or "")
        count = 0 if stored_day != today else _as_int(group.get("interject_today"), 0)
        if count >= max_daily:
            return GateResult(False, "今日群聊插话已达上限")
        return GateResult(True)


class MinIntervalGate(Gate):
    name = "min_interval"

    def check(self, ctx: Context) -> GateResult:
        minutes = _as_float(_cfg(ctx, "group_interject_min_interval_minutes", 0), 0.0)
        if minutes <= 0:
            return GateResult(True)
        last = _as_float(ctx.group.get("last_interject_at"), 0.0)
        if last > ctx.timestamp:
            return GateResult(True)  # clock skew must not silence the bot forever
        if last > 0 and ctx.timestamp - last < minutes * 60:
            return GateResult(False, "群聊插话间隔太近")
        return GateResult(True)


class SameTopicGate(Gate):
    name = "same_topic"

    def __init__(self, signature_fn: Callable[[Any], str] = default_topic_signature) -> None:
        self.signature_fn = signature_fn

    def check(self, ctx: Context) -> GateResult:
        minutes = _as_int(_cfg(ctx, "group_interject_same_topic_cooldown_minutes", 0), 0)
        if minutes <= 0:
            return GateResult(True)
        last = ctx.group.get("last_bot_interjection")
        if not isinstance(last, dict) or not last:
            return GateResult(True)
        signature = _single_line(last.get("topic_signature"), 80)
        last_ts = _as_float(last.get("ts"), 0.0)
        if last_ts > ctx.timestamp:
            return GateResult(True)  # future timestamp = clock skew, fail open
        if (
            signature
            and last_ts > 0
            and ctx.timestamp - last_ts < minutes * 60
            and signature == self.signature_fn(ctx.text)
        ):
            return GateResult(False, "同一话题刚接过话")
        return GateResult(True)


@dataclass
class ConsultThrottleGate(Gate):
    """Seconds-level consult throttle; the per-group timestamp map is injected."""

    window_seconds: int
    store: dict = field(default_factory=dict)
    name = "consult_throttle"

    def check(self, ctx: Context) -> GateResult:
        window = min(3600, max(0, int(self.window_seconds)))  # production clamps [0,3600]
        if window <= 0:
            return GateResult(True)
        group_id = ctx.group_id
        last = _as_float(self.store.get(group_id), 0.0)
        if last > ctx.timestamp:
            self.store[group_id] = ctx.timestamp  # reset a future/stale clock entry
            return GateResult(True)
        if last > 0 and ctx.timestamp - last < window:
            wait = int(window - (ctx.timestamp - last)) + 1
            return GateResult(False, "裁判咨询节流", wait_seconds=wait)
        self.store[group_id] = ctx.timestamp
        return GateResult(True)


class LegacyDiceGate(Gate):
    """The pre-2026-09-30 dice path, kept for rollback (judge_decides=False)."""

    name = "legacy_dice"
    _OPEN_ENDED = re.compile(r"(有没有人|谁懂|救命|怎么回事|咋办)")
    _JOKE = re.compile(r"(笑死|绷不住|太离谱)")

    def check(self, ctx: Context) -> GateResult:
        if bool(_cfg(ctx, "group_interject_judge_decides", True)):
            return GateResult(True, "交由裁判判断")
        override = _cfg(ctx, "legacy_probability_override", None)
        if override is not None:
            probability = max(0.0, min(1.0, _as_float(override, 0.0)))
            reason = "legacy override"
        else:
            atmosphere = ctx.group.get("atmosphere") if isinstance(ctx.group.get("atmosphere"), dict) else {}
            mood = str(atmosphere.get("mood") or "")
            pace = str(atmosphere.get("pace") or "")
            if self._OPEN_ENDED.search(ctx.text):
                probability, reason = 0.055, "有开放式接话口"
            elif self._JOKE.search(ctx.text):
                probability, reason = (0.018 if mood == "玩笑" else 0.008), "玩笑反应口"
            elif mood == "玩笑":
                probability, reason = 0.015, "玩笑气氛"
            elif mood == "求助":
                probability, reason = 0.035, "求助气氛"
            elif pace == "热闹":
                probability, reason = 0.012, "热闹气氛轻接一句"
            else:
                return GateResult(False, "没有自然插话口")
            multiplier = 1.0
            if bool(_cfg(ctx, "group_busy_timing_enabled", True)):
                multiplier *= relative_budget(ctx.group)
            multiplier *= _as_float(_cfg(ctx, "legacy_weight", 1.0), 1.0)
            probability = max(0.0, min(1.0, probability * multiplier))
        roll = stable_roll(
            ctx.group_id,
            ctx.message_id,
            ctx.timestamp,
            _single_line(ctx.text, 120),
        )
        return GateResult(roll < probability, reason)


def default_gates(
    config: Mapping[str, Any] | None = None,
    *,
    throttle_store: dict | None = None,
) -> list[Gate]:
    """The production order: hard vetoes first, then caps/throttles, then dice.

    Pass the same ``throttle_store`` across calls (or hold the
    :class:`ConsultThrottleGate` instance) for the consult throttle to persist.
    """
    config = dict(config or {})
    throttle_store = {} if throttle_store is None else throttle_store
    consult_window = min(
        3600,
        max(0, _as_int(config.get("group_interject_judge_min_consult_seconds", 40), 40)),
    )
    return [
        EnabledGate(),
        ExplicitDirectionGate(),
        DoNotInterruptGate(),
        DailyCapGate(),
        MinIntervalGate(),
        SameTopicGate(),
        ConsultThrottleGate(window_seconds=consult_window, store=throttle_store),
        LegacyDiceGate(),
    ]
