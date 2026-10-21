"""Structured metrics + dependency-free charts (M3)."""
from .metrics import MetricEvent, MetricsCollector, percentile, read_jsonl, write_jsonl
from .render import bar_chart_svg, render_html, render_svg, write_report

__all__ = [
    "MetricEvent",
    "MetricsCollector",
    "percentile",
    "read_jsonl",
    "write_jsonl",
    "bar_chart_svg",
    "render_html",
    "render_svg",
    "write_report",
]
