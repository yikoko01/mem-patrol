"""Render a metrics report from a JSONL event file (M3 "指标能出图")."""
from __future__ import annotations

import argparse
import json
import sys

from .metrics import MetricsCollector, read_jsonl
from .render import write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memorix.observability")
    parser.add_argument("--input", required=True, help="JSONL metric events")
    parser.add_argument("--out", help="report path (.html or .svg)")
    parser.add_argument("--json", action="store_true", help="print the snapshot as JSON")
    args = parser.parse_args(argv)
    collector = MetricsCollector()
    for event in read_jsonl(args.input):
        collector.record(event)
    snapshot = collector.snapshot()
    if args.json or not args.out:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    if args.out:
        path = write_report(snapshot, args.out)
        print("REPORT %s" % path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
