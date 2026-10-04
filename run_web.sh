#!/usr/bin/env bash
# Diamond Scorer -- web (browser) launcher for macOS / Linux.
# Binds to localhost only by default. See run_web.py for the security note.
set -euo pipefail
cd "$(dirname "$0")"

# Pick a Python 3 interpreter.
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi

# Create / reuse a local virtualenv so dependencies stay isolated.
if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip >/dev/null
  pip install -r requirements.txt
else
  . .venv/bin/activate
fi

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"
exec python run_web.py
