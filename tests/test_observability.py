"""M3 metrics: aggregation, percentiles, JSONL, SVG/HTML rendering."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from memorix.observability import (
    MetricEvent,
    MetricsCollector,
    bar_chart_svg,
    percentile,
    read_jsonl,
    render_html,
    render_svg,
    write_jsonl,
    write_report,
)
from memorix.observability.__main__ import main as observability_main


def test_metric_event_roundtrip():
    event = MetricEvent(kind="judge", outcome="sent", reason="ok", latency_ms=12.5, cost_usd=0.01)
    assert MetricEvent.from_dict(event.to_dict()) == event


def test_percentile():
    assert percentile([], 0.5) is None
    assert percentile([10], 0.9) == 10.0
    assert percentile([0, 10], 0.5) == 5.0
    assert percentile([1, 2, 3, 4], 0.5) == 2.5
    assert percentile([1, 2, 3, 4], 1.0) == 4.0


def test_collector_snapshot():
    collector = MetricsCollector()
    for latency in (10.0, 20.0, 30.0):
        collector.record_decision(outcome="sent", reason="judge_allowed", latency_ms=latency, source="g")
    collector.record_decision(outcome="dropped", reason="今日群聊插话已达上限", latency_ms=0.0)
    collector.record_recall(hit=True, top_k=3, latency_ms=2.0, chars=120)
    collector.record_recall(hit=False, top_k=0, latency_ms=1.0)
    collector.record_patrol(action="SKIP", count=0, latency_ms=4.0)
    collector.record(
        MetricEvent(kind="judge", outcome="sent", tokens_in=10, tokens_out=5, cost_usd=0.002)
    )
    snapshot = collector.snapshot()
    assert snapshot["events"] == 8
    assert snapshot["by_kind"] == {"judge": 5, "patrol": 1, "recall": 2}
    assert snapshot["outcomes"]["judge:sent"] == 4
    assert snapshot["reasons"]["judge_allowed"] == 3
    assert snapshot["latency_ms"]["judge"]["p50"] == 15.0  # 0,10,20,30 -> p50=15 (0ms counted)
    assert snapshot["tokens_in"] == 10 and snapshot["tokens_out"] == 5
    assert snapshot["recall_top_k"] == 3 and snapshot["recall_chars"] == 120
    assert snapshot["rejection_reasons"] == {"今日群聊插话已达上限": 1}
    assert snapshot["cost_usd"] == 0.002


def test_jsonl_roundtrip(tmp_path):
    path = tmp_path / "events.jsonl"
    events = [MetricEvent("judge", "sent"), MetricEvent("recall", "hit", latency_ms=0.0)]
    write_jsonl(path, events)
    assert read_jsonl(path) == events
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_bar_chart_is_valid_svg():
    svg = bar_chart_svg({"a": 3, "b": 1}, title="outcomes")
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    text = "".join(node.text or "" for node in root.iter())
    assert "outcomes" in text and "a" in text and "3" in text


def test_render_svg_and_html():
    snapshot = MetricsCollector().snapshot()
    assert "svg" in render_svg(snapshot).lower()
    collector = MetricsCollector()
    collector.record_decision(outcome="sent", latency_ms=10.0)
    collector.record_decision(outcome="dropped", reason="x", latency_ms=20.0)
    snapshot = collector.snapshot()
    svg = render_svg(snapshot)
    ET.fromstring(svg)
    html = render_html(snapshot)
    assert "<table>" in html and "judge:sent" in html


def test_write_report(tmp_path):
    collector = MetricsCollector()
    collector.record_decision(outcome="sent")
    snapshot = collector.snapshot()
    svg_path = write_report(snapshot, tmp_path / "r.svg")
    html_path = write_report(snapshot, tmp_path / "r.html")
    assert svg_path.read_text(encoding="utf-8").startswith("<svg")
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_observability_cli(tmp_path):
    events = tmp_path / "events.jsonl"
    write_jsonl(events, [MetricEvent("judge", "sent", latency_ms=5.0)])
    out = tmp_path / "report.html"
    assert observability_main(["--input", str(events), "--out", str(out)]) == 0
    assert out.exists() and "judge:sent" in out.read_text(encoding="utf-8")
    assert observability_main(["--input", str(events), "--json"]) == 0


def test_zero_latency_is_counted_not_dropped():
    collector = MetricsCollector()
    collector.record_decision(outcome="sent", latency_ms=0.0)
    snapshot = collector.snapshot()
    assert snapshot["latency_ms"]["judge"]["p50"] == 0.0


def test_rejection_reasons_exclude_allowed():
    collector = MetricsCollector()
    collector.record_decision(outcome="sent", reason="judge_allowed")
    collector.record_decision(outcome="dropped", reason="no_value")
    snapshot = collector.snapshot()
    assert snapshot["reasons"] == {"judge_allowed": 1, "no_value": 1}
    assert snapshot["rejection_reasons"] == {"no_value": 1}
