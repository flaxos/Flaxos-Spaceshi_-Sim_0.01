# Docs Index

This directory contains both current operational docs and historical design/reference material.

## Current Docs

- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md): verified ten-task merge/evidence status, pending human acceptance and owner decisions
- [SHARED_SHIP_PLAYTEST.md](SHARED_SHIP_PLAYTEST.md): isolated current-main checkout and two-person/solo exercise
- [FIRST_TUTORIAL_DOCKING_GUIDANCE.md](FIRST_TUTORIAL_DOCKING_GUIDANCE.md): merged first-tutorial instructions and human verification

- [UAT_MASTER_PLAN.md](UAT_MASTER_PLAN.md): full human UAT ladder, mission order, and log-monitoring guidance
- [UAT_COMMANDS.md](UAT_COMMANDS.md): exact copy/paste command set for UAT
- [STATION_UAT_WIRING_CHECKLIST.md](STATION_UAT_WIRING_CHECKLIST.md): fast smoke and bridge wiring triage
- [MOBILE_GUI_TESTING.md](MOBILE_GUI_TESTING.md): current mobile/browser checklist for the Svelte UI
- [USER_GUIDE.md](USER_GUIDE.md): current player/operator guidance
- [ARCHITECTURE.md](ARCHITECTURE.md): current stack and subsystem architecture
- [API_REFERENCE.md](API_REFERENCE.md): command and payload reference

## Historical / Reference Docs

These are still useful, but they should not be treated as the source of truth for the current Svelte bridge UI:

- [GUI_DEV_PLAN.md](GUI_DEV_PLAN.md)
- [NAV_HELM_GUI_TEST_PLAN.md](NAV_HELM_GUI_TEST_PLAN.md)
- [SPRINT_RECOMMENDATIONS.md](SPRINT_RECOMMENDATIONS.md)
- [S3_PREPARATION.md](S3_PREPARATION.md)

## Operational Scripts

- `python3 tools/check_station_wiring.py`
- `python3 tools/uat_monitor.py --follow --fail-on-critical`
- `tools/uat_commands.sh`
- `node tools/gui_smoke_check.js --start-stack`

The last command is the legacy CPU debug smoke. The repeatable current-Svelte
crew mode remains in draft PR423; use the checklist's pinned instructions.
