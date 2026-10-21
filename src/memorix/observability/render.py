"""Dependency-free charts: SVG bar charts + an HTML report (M3 "指标能出图")."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Mapping

_WIDTH = 520
_ROW = 24
_MARGIN_LEFT = 150
_MARGIN_TOP = 34
_MARGIN_BOTTOM = 12


def bar_chart_svg(
    data: Mapping[str, float],
    *,
    title: str = "",
    width: int = _WIDTH,
    row_height: int = _ROW,
    max_bars: int = 12,
) -> str:
    """A self-contained SVG horizontal bar chart."""
    items = list(data.items())[: max(0, int(max_bars))]
    height = _MARGIN_TOP + max(1, len(items)) * row_height + _MARGIN_BOTTOM
    maximum = max((float(value) for _, value in items), default=0.0) or 1.0
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" aria-label="%s">'
        % (width, height, width, height, escape(title or "chart", quote=True)),
        '<rect width="100%%" height="100%%" fill="#0f172a"/>',
    ]
    if title:
        parts.append(
            '<text x="12" y="22" fill="#e2e8f0" font-family="sans-serif" font-size="14">%s</text>'
            % escape(title)
        )
    bar_width = max(20, width - _MARGIN_LEFT - 24)
    for index, (label, value) in enumerate(items):
        y = _MARGIN_TOP + index * row_height
        fraction = max(0.0, min(1.0, float(value) / maximum))
        parts.append(
            '<text x="12" y="%d" fill="#cbd5e1" font-family="sans-serif" font-size="12">%s</text>'
            % (y + 15, escape(str(label)[:24]))
        )
        parts.append(
            '<rect x="%d" y="%d" width="%d" height="%d" fill="#38bdf8" rx="3"/>'
            % (_MARGIN_LEFT, y + 4, int(bar_width * fraction), row_height - 8)
        )
        parts.append(
            '<text x="%d" y="%d" fill="#f1f5f9" font-family="monospace" font-size="11">%s</text>'
            % (_MARGIN_LEFT + int(bar_width * fraction) + 6, y + 16, escape(_fmt(value)))
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _fmt(value: float) -> str:
    number = float(value)
    if number >= 1000:
        return "%.0f" % number
    if number != int(number):
        return "%.2f" % number
    return str(int(number))


def _charts(snapshot: Mapping) -> list[str]:
    charts: list[str] = []
    outcomes = snapshot.get("outcomes") or {}
    if outcomes:
        charts.append(bar_chart_svg(dict(outcomes), title="decisions by outcome"))
    reasons = snapshot.get("rejection_reasons") or {}
    if reasons:
        charts.append(bar_chart_svg(dict(list(reasons.items())[:10]), title="top rejection reasons"))
    latency = snapshot.get("latency_ms") or {}
    for kind, values in latency.items():
        points = {key: value for key, value in values.items() if value is not None}
        if points:
            charts.append(bar_chart_svg(points, title="%s latency (ms)" % kind))
    return charts


def render_svg(snapshot: Mapping) -> str:
    """Stack all charts into one SVG document."""
    charts = _charts(snapshot)
    if not charts:
        return bar_chart_svg({}, title="no data")
    bodies = []
    for chart in charts:
        body = chart.split(">", 1)[1].rsplit("</svg>", 1)[0]
        bodies.append(body)
    width = _WIDTH
    height = sum(int(chart.split('height="', 1)[1].split('"', 1)[0]) for chart in charts)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (width, height, width, height)
        + "".join(bodies)
        + "</svg>"
    )


def render_html(snapshot: Mapping, *, title: str = "memorix metrics") -> str:
    rows = []
    for key in ("events", "by_kind", "outcomes", "reasons", "tokens_in", "tokens_out", "cost_usd"):
        rows.append(
            "<tr><th>%s</th><td><code>%s</code></td></tr>"
            % (escape(key), escape(str(snapshot.get(key))))
        )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>%s</title>"
        "<style>body{background:#0f172a;color:#e2e8f0;font-family:sans-serif}"
        "table{border-collapse:collapse}th,td{padding:4px 8px;border:1px solid #334155}"
        "</style></head><body><h1>%s</h1><table>%s</table><h2>charts</h2>%s</body></html>"
        % (escape(title), escape(title), "".join(rows), render_svg(snapshot))
    )


def write_report(snapshot: Mapping, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)
    elif path.suffix.lower() == ".svg":
        text = render_svg(snapshot)
    else:
        text = render_html(snapshot)
    path.write_text(text, encoding="utf-8")
    return path
