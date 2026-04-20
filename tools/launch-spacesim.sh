#!/usr/bin/env bash
# Flaxos Spaceship Sim — Shell Launcher (shim)
# Delegates to tools/launch.py which is the canonical entry point.
# Use: python tools/launch.py [args]  for the full interactive experience.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$PROJECT_DIR/.venv"
LAUNCHER="$PROJECT_DIR/tools/launch.py"

# Activate venv if present
if [ -f "$VENV/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
fi

echo "[launch] Delegating to tools/launch.py ..."
exec python "$LAUNCHER" "$@"
