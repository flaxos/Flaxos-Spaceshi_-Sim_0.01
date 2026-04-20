#!/usr/bin/env bash
# Flaxos Spaceship Sim — Interactive Launcher (shim)
# The full interactive flow now lives in tools/launch.py directly.
# This script just invokes it with no extra flags (wizard runs automatically).

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$PROJECT_DIR/tools/launch-spacesim.sh" "$@"
