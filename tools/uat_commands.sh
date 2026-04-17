#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage:
  tools/uat_commands.sh
  tools/uat_commands.sh print
  tools/uat_commands.sh start <rcon-password>
  tools/uat_commands.sh smoke
  tools/uat_commands.sh tactical
  tools/uat_commands.sh ops
  tools/uat_commands.sh science
  tools/uat_commands.sh monitor

Modes:
  print     Print the standard UAT commands and mission docs
  start     Launch the default Svelte stack with browser + RCON password
  smoke     Run station wiring smoke checks (helm/tutorial)
  tactical  Run tactical command sweep (Phase 2: combat, railgun, torpedoes, missiles)
  ops       Run ops/engineering/stealth command sweep (Phase 3: repair, power, EMCON)
  science   Run science/comms command sweep (Phase 4: analysis, hail, broadcast)
  monitor   Tail the latest session log and fail on critical patterns
EOF
}

print_commands() {
  cat <<'EOF'
Flaxos Spaceship Sim UAT Commands

1. Start the stack
python3 tools/start_gui_stack.py --browser --rcon-password 'replace-this'

2. Run the fast bridge smoke (Phase 0-1: shell + helm)
python3 tools/check_station_wiring.py

3. Run the tactical command sweep (Phase 2: combat, railgun, torpedoes, missiles)
python3 tools/uat_command_sweep.py

4. Run the ops/engineering/stealth sweep (Phase 3: repair, power, EMCON)
python3 tools/uat_ops_sweep.py

5. Run the science/comms sweep (Phase 4: analysis, hail, broadcast)
python3 tools/uat_science_comms_sweep.py

6. Watch logs during UAT in a second terminal
python3 tools/uat_monitor.py --follow --fail-on-critical

6. UAT docs
docs/UAT_MASTER_PLAN.md
docs/STATION_UAT_WIRING_CHECKLIST.md
docs/MOBILE_GUI_TESTING.md
docs/UAT_COMMANDS.md
EOF
}

mode="${1:-print}"

case "$mode" in
  print)
    print_commands
    ;;
  start)
    if [[ $# -lt 2 ]]; then
      echo "error: start mode requires an RCON password" >&2
      usage >&2
      exit 1
    fi
    exec python3 tools/start_gui_stack.py --browser --rcon-password "$2"
    ;;
  smoke)
    exec python3 tools/check_station_wiring.py
    ;;
  tactical)
    exec python3 tools/uat_command_sweep.py
    ;;
  ops)
    exec python3 tools/uat_ops_sweep.py
    ;;
  science)
    exec python3 tools/uat_science_comms_sweep.py
    ;;
  monitor)
    exec python3 tools/uat_monitor.py --follow --fail-on-critical
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "error: unknown mode: $mode" >&2
    usage >&2
    exit 1
    ;;
esac
