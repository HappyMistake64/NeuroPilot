#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
rsi_python="python3"
if [[ -x .venv/bin/python ]]; then rsi_python=".venv/bin/python"; fi
"$rsi_python" -m rsi init
exec "$rsi_python" server.py
