#!/usr/bin/env bash
# Deterministischer Testlauf: Selftest (L1) + pytest (inkl. M1-Baseline-Regression).
# Nutzt die venv. Auf Windows via Git-Bash ausführen: bash scripts/test.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# venv-Python finden (Windows: .venv/Scripts, POSIX: .venv/bin).
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  echo "Keine venv gefunden — bitte 'py -m venv .venv' und Deps installieren." >&2
  exit 1
fi

echo "== L1 Selftest =="
"$PY" boardview_mcp.py --selftest >/dev/null
echo "OK: boardview_mcp.py --selftest"

echo "== pytest =="
"$PY" -m pytest -q
