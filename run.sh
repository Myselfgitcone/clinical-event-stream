#!/usr/bin/env bash
# One command, end to end. Needs Python 3.11+ and Java 17 on PATH.
#   ./run.sh            2,000 patients, seed 20261118
#   ./run.sh 200        quicker
set -euo pipefail
cd "$(dirname "$0")"
PATIENTS="${1:-2000}"
SEED="${2:-20261118}"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[dev]"
fi
.venv/bin/python -m ces run --patients "$PATIENTS" --seed "$SEED" --no-extend
echo
echo "done. open the page with:  .venv/bin/python -m http.server -d site 8000"
