# Docs Index

This directory contains both current operational docs and historical design/reference material.

## Current Docs

- [UAT_MASTER_PLAN.md](/home/flax/games/spaceship-sim/docs/UAT_MASTER_PLAN.md): full human UAT ladder, mission order, and log-monitoring guidance
- [UAT_COMMANDS.md](/home/flax/games/spaceship-sim/docs/UAT_COMMANDS.md): exact copy/paste command set for UAT
- [STATION_UAT_WIRING_CHECKLIST.md](/home/flax/games/spaceship-sim/docs/STATION_UAT_WIRING_CHECKLIST.md): fast smoke and bridge wiring triage
- [MOBILE_GUI_TESTING.md](/home/flax/games/spaceship-sim/docs/MOBILE_GUI_TESTING.md): current mobile/browser checklist for the Svelte UI
- [USER_GUIDE.md](/home/flax/games/spaceship-sim/docs/USER_GUIDE.md): current player/operator guidance
- [ARCHITECTURE.md](/home/flax/games/spaceship-sim/docs/ARCHITECTURE.md): current stack and subsystem architecture
- [API_REFERENCE.md](/home/flax/games/spaceship-sim/docs/API_REFERENCE.md): command and payload reference

## Historical / Reference Docs

These are still useful, but they should not be treated as the source of truth for the current Svelte bridge UI:

- [GUI_DEV_PLAN.md](/home/flax/games/spaceship-sim/docs/GUI_DEV_PLAN.md)
- [NAV_HELM_GUI_TEST_PLAN.md](/home/flax/games/spaceship-sim/docs/NAV_HELM_GUI_TEST_PLAN.md)
- [SPRINT_RECOMMENDATIONS.md](/home/flax/games/spaceship-sim/docs/SPRINT_RECOMMENDATIONS.md)
- [S3_PREPARATION.md](/home/flax/games/spaceship-sim/docs/S3_PREPARATION.md)

## Operational Scripts

- `python3 tools/check_station_wiring.py`
- `python3 tools/uat_monitor.py --follow --fail-on-critical`
- `tools/uat_commands.sh`
- `node tools/gui_smoke_check.js --start-stack`
