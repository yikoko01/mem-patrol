#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DB=/tmp/mem-patrol-demo/demo.db
${PYTHON:-python3} scripts/demo_setup.py "$DB" >/dev/null
PYTHONPATH=src ${PYTHON:-python3} -m memorix --version
echo
PYTHONPATH=src ${PYTHON:-python3} -m memorix diagnose --db "$DB" --now 1792000100
echo
PYTHONPATH=src ${PYTHON:-python3} -m memorix.retrieval.bench
echo
PYTHONPATH=src ${PYTHON:-python3} -m memorix recall --db "$DB" --user-id demo-user --query "8-23 比 8-19 更难"
