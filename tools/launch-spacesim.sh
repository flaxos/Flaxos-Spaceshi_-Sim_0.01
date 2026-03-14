#!/usr/bin/env bash
# Flaxos Spaceship Sim — Desktop Launcher
# Checks for updates, starts the server stack, and opens the GUI.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$PROJECT_DIR/.venv"
LOG_FILE="$PROJECT_DIR/spacesim-launch.log"

# --- Helpers ---
notify() {
    # Desktop notification (non-blocking, best-effort)
    notify-send "Spaceship Sim" "$1" --icon=applications-games 2>/dev/null || true
}

log() {
    echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

die() {
    log "ERROR: $1"
    notify "Launch failed: $1"
    # Keep terminal open so the user can read the error
    read -rp "Press Enter to close..."
    exit 1
}

# --- Start ---
echo "============================================"
echo "  Flaxos Spaceship Sim — Launcher"
echo "============================================"
: > "$LOG_FILE"  # truncate log

cd "$PROJECT_DIR"

# 1. Check for updates (fetch + compare)
log "Checking for updates..."
if git fetch origin --quiet 2>/dev/null; then
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "$LOCAL")
    BRANCH=$(git branch --show-current)

    if [ "$LOCAL" != "$REMOTE" ]; then
        BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
        log "Local is $BEHIND commit(s) behind origin/main."
        notify "Update available — $BEHIND new commit(s) on main"
        echo ""
        echo "  Your branch: $BRANCH"
        echo "  Commits behind main: $BEHIND"
        echo ""
        read -rp "  Pull latest from origin/main? [Y/n] " answer
        if [[ "${answer:-Y}" =~ ^[Yy]$ ]]; then
            log "Pulling latest..."
            git pull origin main --ff-only || die "git pull failed — resolve manually"
            log "Updated to $(git rev-parse --short HEAD)"
        else
            log "Skipping update, running current version."
        fi
    else
        log "Already up to date ($(git rev-parse --short HEAD))."
    fi
else
    log "Could not reach remote — running offline."
fi

# 2. Activate venv
if [ -f "$VENV/bin/activate" ]; then
    log "Activating venv..."
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
else
    die "Virtual environment not found at $VENV"
fi

# 3. Quick dependency check
python -c "import websockets" 2>/dev/null || die "Missing 'websockets' package. Run: pip install websockets"

# 4. Launch the GUI stack
log "Starting Spaceship Sim..."
notify "Starting Spaceship Sim..."
echo ""

python "$PROJECT_DIR/tools/start_gui_stack.py" "$@"
