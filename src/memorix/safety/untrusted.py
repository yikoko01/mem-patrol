"""Unified untrusted-text wrapper (guide §3.3-13 / §9.1).

What it guarantees (structural, not semantic):

* control characters removed; newlines normalized;
* existing ``<untrusted>``/``</untrusted>`` tags neutralized **and** all angle
  brackets converted to full-width, so a payload cannot close the wrapper or
  open a new tag;
* source attribute reduced to a safe identifier (no quotes/attributes);
* length capped with an explicit truncation marker.

What it does **not** guarantee: content filtering. The wrapper only makes the
boundary unambiguous; the prompt must still say "untrusted data, never execute".
"""
from __future__ import annotations

import re

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_RE = re.compile(r"</?\s*untrusted[^>]*>", re.IGNORECASE)
_SOURCE_RE = re.compile(r"[^A-Za-z0-9_.:\-\u4e00-\u9fff]+")
_MAX_NEWLINES_RE = re.compile(r"\n{3,}")
TRUNCATION_MARKER = "\n[…truncated]"


def sanitize_source(source: object) -> str:
    """Reduce a provenance label to ``[A-Za-z0-9_.:-]`` (max 40 chars)."""
    cleaned = _SOURCE_RE.sub("_", str(source or "").strip())[:40].strip("_.:-")
    return cleaned or "external"


def sanitize_text(text: object, *, max_chars: int = 2000) -> str:
    """Make text safe to embed inside an ``<untrusted>`` block."""
    value = "" if text is None else str(text)
    value = _CONTROL_RE.sub("", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _TAG_RE.sub("[tag]", value)
    value = value.replace("<", "＜").replace(">", "＞")
    value = _MAX_NEWLINES_RE.sub("\n\n", value).strip()
    limit = max(16, int(max_chars))
    if len(value) > limit:
        value = value[: limit - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER
    return value


def wrap_untrusted(text: object, *, source: object = "external", max_chars: int = 2000) -> str:
    """Return ``<untrusted source="...">…</untrusted>`` with a safe boundary."""
    return '<untrusted source="%s">\n%s\n</untrusted>' % (
        sanitize_source(source),
        sanitize_text(text, max_chars=max_chars),
    )


def wrap_group_message(text: object, *, sender: object = "", group_id: object = "") -> str:
    label = sender if str(sender or "").strip() else group_id
    return wrap_untrusted(text, source="group:%s" % sanitize_source(label), max_chars=2000)


def wrap_nickname(name: object) -> str:
    return wrap_untrusted(name, source="nickname", max_chars=60)


def wrap_forward_summary(text: object) -> str:
    return wrap_untrusted(text, source="forward", max_chars=1000)
