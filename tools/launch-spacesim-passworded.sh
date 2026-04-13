#!/usr/bin/env bash
# Flaxos Spaceship Sim — Password Prompt Launcher
# Prompts for an RCON password, then launches the standard stack launcher.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BASE_LAUNCHER="$PROJECT_DIR/tools/launch-spacesim.sh"

notify() {
    notify-send "Spaceship Sim" "$1" --icon=applications-games 2>/dev/null || true
}

die() {
    echo "ERROR: $1" >&2
    notify "Launch failed: $1"
    read -rp "Press Enter to close..."
    exit 1
}

have_zenity() {
    command -v zenity >/dev/null 2>&1
}

prompt_password() {
    local prompt="$1"
    local value=""

    if have_zenity; then
        value="$(zenity --password --title="Spaceship Sim" --text="$prompt")" || return 1
        printf '%s' "$value"
        return 0
    fi

    read -rsp "$prompt: " value || return 1
    echo
    printf '%s' "$value"
}

prompt_text() {
    local prompt="$1"
    local value=""

    if have_zenity; then
        value="$(zenity --entry --title="Spaceship Sim" --text="$prompt")" || return 1
        printf '%s' "$value"
        return 0
    fi

    read -rp "$prompt: " value || return 1
    printf '%s' "$value"
}

confirm_yes_no() {
    local prompt="$1"

    if have_zenity; then
        zenity --question --title="Spaceship Sim" --text="$prompt"
        return $?
    fi

    local answer=""
    read -rp "$prompt [y/N]: " answer || return 1
    [[ "$answer" =~ ^[Yy]$ ]]
}

for attempt in 1 2 3; do
    RCON_PASSWORD="$(prompt_password "Enter the RCON password for Mission > Server")" || exit 0
    [[ -n "$RCON_PASSWORD" ]] || {
        notify "RCON password cannot be empty"
        continue
    }

    CONFIRM_PASSWORD="$(prompt_password "Confirm the RCON password")" || exit 0
    if [[ "$RCON_PASSWORD" == "$CONFIRM_PASSWORD" ]]; then
        break
    fi

    notify "Passwords did not match"
    if [[ "$attempt" -eq 3 ]]; then
        die "RCON password confirmation failed three times"
    fi
done

LAUNCH_ARGS=(--browser)

if confirm_yes_no "Enable LAN / ZeroTier mode?"; then
    ZT_HOSTS="$(prompt_text "Optional: enter ZeroTier IPs or hostnames to allow (comma-separated). localhost stays allowed automatically.")" || exit 0
    GAME_CODE="$(prompt_text "Optional: enter a shared game code (leave blank to auto-generate)")" || exit 0

    LAUNCH_ARGS+=(--lan --allowed-origin-host "localhost")
    if [[ -n "${ZT_HOSTS// }" ]]; then
        IFS=',' read -r -a ZT_HOST_ARRAY <<< "$ZT_HOSTS"
        for host in "${ZT_HOST_ARRAY[@]}"; do
            host="$(printf '%s' "$host" | xargs)"
            [[ -n "$host" ]] || continue
            LAUNCH_ARGS+=(--allowed-origin-host "$host")
        done
    fi

    if [[ -n "$GAME_CODE" ]]; then
        LAUNCH_ARGS+=(--game-code "$GAME_CODE")
    fi
fi

export FLAXOS_RCON_PASSWORD="$RCON_PASSWORD"
exec "$BASE_LAUNCHER" "${LAUNCH_ARGS[@]}"
