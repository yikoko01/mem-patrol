"""Read-only integration check against an arbitrary SQLite memory DB.

Use a copy of the DB, never production directly. No writes are performed.

    python scripts/integration_check.py --db /tmp/copy.db --schema auto
    python scripts/integration_check.py --db /tmp/copy.db --schema schema.json \
      --user-id <id> --query "为什么..."
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def run(*args: str) -> tuple[int, str]:
    completed = subprocess.run(
        [sys.executable, "-m", "memorix", *args], capture_output=True, text=True
    )
    return completed.returncode, (completed.stdout or completed.stderr).strip()


def brief(text: str, max_lines: int = 2) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    return "\n".join(lines[-max_lines:])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--schema", default="auto")
    parser.add_argument("--user-id", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--verbose", action="store_true", help="print full command output on failure")
    args = parser.parse_args(argv)
    failures = 0
    code, out = run("--version")
    print("==", "version", "==", out or "(no output)")
    if code:
        return 1
    code, out = run("doctor", "--db", args.db, "--schema", args.schema, "--json")
    print("==", "doctor", "==")
    try:
        doctor = json.loads(out)
        print("ok:", doctor.get("ok"), "clean:", doctor.get("clean"), "warnings:", len(doctor.get("warnings", [])))
        for warning in doctor.get("warnings", []):
            print("WARN:", warning)
        for problem in doctor.get("problems", []):
            print("PROBLEM:", problem)
            failures += 1
    except Exception:
        print(brief(out) if not args.verbose else out)
        failures += 1
    code, out = run("diagnose", "--db", args.db, "--schema", args.schema, "--json")
    print("==", "diagnose", "==")
    if code:
        print(brief(out) if not args.verbose else out)
        failures += 1
    else:
        try:
            diag = json.loads(out)
            print("total:", diag.get("total"), "findings:", len(diag.get("findings", [])))
        except Exception:
            print(brief(out) if not args.verbose else out)
    if args.query:
        code, out = run(
            "recall", "--db", args.db, "--schema", args.schema, "--query", args.query,
            "--user-id", args.user_id, "--json",
        )
        print("==", "recall", "==")
        if code:
            print(brief(out) if not args.verbose else out)
            failures += 1
        else:
            data = json.loads(out)
            print("ids:", data.get("memory_ids"), "chars:", len(data.get("text", "")))
            if not data.get("memory_ids"):
                print("NOTE: empty recall (lexical boundary or no matching memory)")
    print("INTEGRATION_%s" % ("PASS" if failures == 0 else "FAIL"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
