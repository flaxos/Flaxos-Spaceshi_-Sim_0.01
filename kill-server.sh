#!/usr/bin/env bash
# Kill all running spaceship-sim server processes.
# Usage: ./kill-server.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Looking for spaceship-sim processes..."

killed=0

# Kill the GUI stack launcher
for pid in $(pgrep -f "start_gui_stack.py" 2>/dev/null || true); do
    echo "  Killing GUI launcher (PID $pid)"
    kill "$pid" 2>/dev/null && ((killed++)) || true
done

# Kill the main server
for pid in $(pgrep -f "server\.main" 2>/dev/null || true); do
    echo "  Killing server (PID $pid)"
    kill "$pid" 2>/dev/null && ((killed++)) || true
done

# Kill the WS bridge
for pid in $(pgrep -f "ws_bridge\.py" 2>/dev/null || true); do
    echo "  Killing WS bridge (PID $pid)"
    kill "$pid" 2>/dev/null && ((killed++)) || true
done

# Kill the HTTP server on port 3100
for pid in $(pgrep -f "http\.server 3100" 2>/dev/null || true); do
    echo "  Killing HTTP server (PID $pid)"
    kill "$pid" 2>/dev/null && ((killed++)) || true
done

if [ "$killed" -eq 0 ]; then
    echo "No spaceship-sim processes found."
else
    echo "Killed $killed process(es)."
fi
