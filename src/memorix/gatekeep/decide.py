"""Decision contract + pipeline (no LLM, no host).

``decide(ctx, judge=...)`` runs the deterministic gates, then hands the trigger
to an injected judge callable (a stub in tests, the host model in production) and
parses its JSON into :class:`Decision`. The needs-tools routing mirrors
production: directed -> hand back to the main agent (``handoff``), non-directed
-> background tool task (``tool_task``).
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Mapping, Sequence

from .gates import default_gates
from .models import Context, Decision, GateTrace, Outcome

_SINGLE_LINE = lambda value, limit=200: " ".join(str(value or "").split())[:limit]  # noqa: E731
_SILENT_MARKERS = frozenset({
    "空", "空字符串", "空内容", "留空", "无", "没有", "null", "none", "nil", "n/a",
    "不适合说话", "不说", "不回复", "无需回复", "不用回复", "不要回复", "别回复",
    "静默", "忽略",
})
_EXPLICIT_DIRECTED = frozenset({"at_bot", "reply_bot", "mention_bot_name", "explicit_at", "explicit_reply"})


def _json_object(raw: Any) -> dict | None:
    """Parse a JSON object; unlike production this also accepts an already-parsed dict."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def clean_reply(value: Any) -> str:
    """Port of ``_clean_group_interjection_reply`` (80 chars, strip code/quotes)."""
    text = _SINGLE_LINE(value, 80)
    text = re.sub(r"^```(?:text)?|```$", "", text).strip()
    text = text.strip("\"'“”‘’` ")
    compact = re.sub(r"\s+", "", text)
    unwrapped = re.sub(
        r"^[\s\"'“”‘’`(\（\[\【<《「『]+|[\s\"'“”‘’`)\）\]\】>》」』。.!！?？~～…、，,;；:：]+$",
        "",
        compact,
    )
    if not text or compact in _SILENT_MARKERS or unwrapped in _SILENT_MARKERS:
        return ""
    if "空字符串" in unwrapped and len(unwrapped) <= 12:
        return ""
    if re.fullmatch(r"[.。…~～\s\"'“”‘’`-]{1,12}", text):
        return ""
    return text


def parse_needs_tools(raw: Any) -> bool:
    """Port of ``_judge_needs_tools``."""
    payload = _json_object(raw)
    if payload is None:
        return False
    value = payload.get("needs_tools", payload.get("need_tools", payload.get("need_tool")))
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "需要", "要", "是"}
    return bool(value)


def parse_decision(
    raw: Any,
    *,
    meta_leak_checker: Callable[[str], Any] | None = None,
) -> Decision:
    """Port of ``_parse_group_interjection_decision`` to a :class:`Decision`."""
    payload = _json_object(raw)
    if payload is None:
        return Decision(allow=False, reason="invalid_json")

    raw_decision = str(
        payload.get("decision") or payload.get("action") or payload.get("status") or ""
    ).strip().lower()
    raw_should = payload.get("should_reply", payload.get("reply", payload.get("speak")))
    if isinstance(raw_should, str):
        should_text = raw_should.strip().lower()
        should_reply = should_text in {"true", "1", "yes", "y", "reply", "speak", "send", "说", "回复", "发言", "接话"}
        explicit_no = should_text in {"false", "0", "no", "n", "silent", "skip", "drop", "none", "不说", "不回复", "静默"}
    elif raw_should is None:
        should_reply = raw_decision in {"reply", "speak", "send", "say", "接话", "回复", "发言"}
        explicit_no = raw_decision in {"silent", "skip", "drop", "none", "no_reply", "no-reply", "不说", "不回复", "静默"}
    else:
        should_reply = bool(raw_should)
        explicit_no = not should_reply

    if raw_decision in {"silent", "skip", "drop", "none", "no_reply", "no-reply", "不说", "不回复", "静默"}:
        explicit_no = True
    if explicit_no:
        return Decision(False, "", _SINGLE_LINE(payload.get("reason"), 80) or "model_skip")

    reply = clean_reply(
        payload.get("text")
        or payload.get("reply_text")
        or payload.get("message")
        or payload.get("content")
        or ""
    )
    if reply and meta_leak_checker is not None and meta_leak_checker(reply):
        return Decision(False, "", "review_meta_leak")
    return Decision(
        allow=bool(should_reply and reply),
        text=reply if should_reply else "",
        reason=_SINGLE_LINE(payload.get("reason"), 80),
    )


def _is_directed(ctx: Context) -> bool:
    return bool(ctx.directed or ctx.addressed_to_bot or ctx.scene_trigger in _EXPLICIT_DIRECTED)


def decide(
    ctx: Context,
    *,
    gates: Sequence[Any] | None = None,
    judge: Callable[[Context], Any] | None = None,
    shadow: Any = None,
    config: Mapping[str, Any] | None = None,
    metrics: Any = None,
) -> Outcome:
    """Run gates, then (optionally) the judge; return what to do next.

    ``metrics`` (optional) receives one decision event: outcome, reason, latency
    and the group id as source. The kernel stays usable without it.
    """
    started = time.perf_counter()
    outcome = _decide(ctx, gates=gates, judge=judge, shadow=shadow, config=config)
    if metrics is not None:
        metrics.record_decision(
            outcome=outcome.action,
            reason=outcome.reason,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            source=ctx.group_id,
        )
    return outcome


def _decide(
    ctx: Context,
    *,
    gates: Sequence[Any] | None = None,
    judge: Callable[[Context], Any] | None = None,
    shadow: Any = None,
    config: Mapping[str, Any] | None = None,
) -> Outcome:
    """Gate/judge pipeline without instrumentation (see :func:`decide`)."""
    if gates is not None:
        # Explicit caller-provided gates are honoured as-is (custom safety layers).
        active_gates = list(gates)
    elif ctx.directed or ctx.addressed_to_bot:
        # Production parity: a directed trigger (@/reply/name) is handled by the
        # directed fast path, which skips *all* ambient interjection gates and the
        # consult throttle (`group_observation.py`: `if not directed:` guards the
        # whole allowed+consult block). The host's directed-fast-path switch is an
        # adapter concern; this kernel must not re-veto it.
        active_gates = []
    else:
        active_gates = default_gates(config or ctx.config)
    trace: list[GateTrace] = []
    for gate in active_gates:
        result = gate.check(ctx)
        trace.append(GateTrace(gate=getattr(gate, "name", type(gate).__name__), result=result))
        if not result.allowed:
            outcome = Outcome(
                action="dropped",
                decision=Decision(False, reason=result.reason),
                reason=result.reason,
                trace=tuple(trace),
            )
            if shadow is not None:
                shadow.record_call()
            return outcome

    if judge is None:
        if shadow is not None:
            shadow.record_call()
        return Outcome(
            action="candidate",
            decision=Decision(False, reason="no_judge"),
            reason="no judge configured; gates passed",
            trace=tuple(trace),
        )

    raw = judge(ctx)
    decision = parse_decision(raw)
    decision = Decision(
        allow=decision.allow,
        text=decision.text,
        reason=decision.reason,
        needs_tools=parse_needs_tools(raw),
    )
    if not decision.allow:
        action, reason = "dropped", decision.reason or "judge_denied"
    elif decision.needs_tools:
        action, reason = ("handoff" if _is_directed(ctx) else "tool_task"), "needs_tools"
    else:
        action, reason = "sent", decision.reason or "judge_allowed"
    outcome = Outcome(action=action, decision=decision, reason=reason, trace=tuple(trace))
    if shadow is not None:
        shadow.record_call()
    return outcome
