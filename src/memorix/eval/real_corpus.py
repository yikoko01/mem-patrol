"""Privacy-preserving real-corpus regression for the recall scorer.

Stores no production text: a manifest carries a snapshot SHA-256, query strings,
expected memory ids and SHA-256 of each expected memory's normalized content.
Point a read-only snapshot at it and the check reproduces the manual verification.

Usage:
    python -m memorix.eval.real_corpus \
      --db /path/to/snapshot.db --user-id <id> \
      --manifest eval/real_corpus.json \
      --schema examples/self-learning.schema.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from ..retrieval.context import recent_private_context
from ..retrieval.score import recall_scored
from ..retrieval.store import load_rows


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_sha256(text: str) -> str:
    return hashlib.sha256(" ".join(str(text).split()).encode("utf-8")).hexdigest()


def check_corpus(
    db: str | Path,
    *,
    user_id: str,
    manifest: str | Path | dict,
    schema=None,
    verify_hashes: bool = True,
) -> dict:
    if isinstance(manifest, (str, Path)):
        manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
    snapshot = manifest.get("snapshot") or {}
    expected_sha = snapshot.get("sha256")
    actual_sha = sha256_file(db)
    result: dict = {
        "snapshot_sha256": actual_sha,
        "snapshot_matches": (not expected_sha) or actual_sha == expected_sha,
        "queries": [],
        "status": "PASS",
    }
    if expected_sha and actual_sha != expected_sha:
        result["status"] = "FAIL"
        result["queries"].append(
            {"id": "snapshot", "status": "FAIL", "note": "snapshot sha256 mismatch"}
        )
        return result
    for case in manifest.get("queries", []):
        cutoff = case.get("as_of_ts")
        rows = load_rows(db, as_of_ms=(int(cutoff) * 1000) if cutoff else None, schema=schema)
        context = case.get("context", "")
        if not context:
            context = recent_private_context(
                db, user_id, limit=4, schema=schema, as_of_ts=int(cutoff) if cutoff else None
            )
        scored = recall_scored(
            case["query"],
            rows=rows,
            context=context,
            user_id=user_id,
            top_k=max(1, int(case.get("top_n", 3))),
        )
        top_ids = [item.row.id for item in scored[: int(case.get("top_n", 3))]]
        expected = [item["id"] for item in case.get("expected", [])]
        hit = [memory_id for memory_id in expected if memory_id in top_ids]
        item = {
            "id": case["id"],
            "status": "PASS" if hit else "FAIL",
            "top_ids": top_ids,
            "expected_ids": expected,
        }
        if verify_hashes:
            by_id = {row.id: row for row in rows}
            for expected_item in case.get("expected", []):
                wanted = expected_item.get("content_sha256")
                row = by_id.get(int(expected_item["id"]))
                if wanted and row is not None and normalized_sha256(row.content) != wanted:
                    item["status"] = "FAIL"
                    item["note"] = "content hash mismatch for #%s" % expected_item["id"]
        if item["status"] != "PASS":
            result["status"] = "FAIL"
        result["queries"].append(item)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m memorix.eval.real_corpus")
    parser.add_argument("--db", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--manifest", default="eval/real_corpus.json")
    parser.add_argument("--schema", default="examples/self-learning.schema.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = check_corpus(
        args.db,
        user_id=args.user_id,
        manifest=args.manifest,
        schema=args.schema,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("REAL_CORPUS", result["status"])
        for item in result["queries"]:
            print(" ", item["id"], item["status"], "top=", item.get("top_ids"), item.get("note", ""))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
