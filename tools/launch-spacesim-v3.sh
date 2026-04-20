#!/usr/bin/env bash
# Flaxos Spaceship Sim — V3 Quick Launcher (shim)
# Opens browser immediately; use tools/launch.py for full interactive setup.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec "$PROJECT_DIR/tools/launch-spacesim.sh" --quick --browser "$@"
