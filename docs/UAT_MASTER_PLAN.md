# UAT Master Plan

This is the current end-to-end UAT runbook for the default Svelte stack.

Use this document for:
- pre-demo validation
- regression checks after GUI/refactor work
- mobile passes
- live human-operated UAT with log monitoring

If you only need the command set, use [UAT_COMMANDS.md](/home/flax/games/spaceship-sim/docs/UAT_COMMANDS.md).

Use [STATION_UAT_WIRING_CHECKLIST.md](/home/flax/games/spaceship-sim/docs/STATION_UAT_WIRING_CHECKLIST.md) first for fast deterministic smoke. Use this runbook for the full layered pass.

## Current GUI Audit

The current Svelte bridge UI appears to have all major station views wired in:

| Station/View | Current panel groups |
| --- | --- |
| Helm | workflow strip, flight data, contacts, flight computer, manual flight, RCS, queue, docking, planner |
| Tactical | map, contacts, targeting pipeline, firing solution, subsystem targeting, multi-track, railgun/PDC/launcher control, ECM/ECCM, threat board, weapons status, combat log |
| Engineering | thermal, drive, power draw, power allocation, subsystem status, system toggles, event log |
| Ops | ship status, subsystem status, ops control, power profiles, crew fatigue/roster, boarding, drones |
| Science | passive contacts, analysis, manual analysis or arcade minigames |
| Comms | comms control, incoming choices, station chat, passive contacts |
| Fleet | tactical display, roster, formation, orders, shared contacts, fleet fire control |
| Mission / Config | scenario loader, objectives, campaign, command console, server admin |

## Critical Stop Conditions

Stop the pass immediately and treat the build as failed if any of these happen:

1. `tools/check_station_wiring.py` fails.
2. The GUI crashes, hard reloads, or loses the WebSocket repeatedly.
3. `tools/uat_monitor.py` reports a `critical` line or repeated `ERROR` lines.
4. A station can claim but no telemetry updates arrive.
5. `Config > Server` authenticates but pause/time-scale/reset state does not refresh.
6. A command is accepted in the UI but produces no telemetry or log change within 5 seconds.

## Operator Setup

### Stack startup

```bash
python3 tools/start_gui_stack.py --browser --rcon-password 'replace-this'
```

### Fast smoke before UI work

```bash
python3 tools/check_station_wiring.py
```

Expected:
- `PASS loadout`
- `PASS manual`
- `PASS auto`
- `PASS overall`

### Log monitor

In a second terminal:

```bash
python3 tools/uat_monitor.py --follow --fail-on-critical
```

Watch for:
- `Loaded scenario:` on every mission load
- `RCON authenticated` after `Config > Server`
- `Client connected` and station claim lines
- `Mission SUCCESS` / `Mission FAILED`

Stop on:
- `Traceback`
- `ERROR`
- `subprocess exited unexpectedly`
- repeated unauthorized/authentication failures

## Human UAT Order

Run in this order. The sequence is arranged by critical failure depth: shell and wiring first, then core gameplay loops, then specialist stations, then multi-ship stress, then mobile.

### Phase 0: Shell and Admin

#### 0.1 Bridge shell sanity

Actions:
1. Launch the stack and load the Svelte UI.
2. Confirm `StatusBar`, station selector, tier selector, and view tabs render.
3. Open devtools and run `_flaxosDebugState()`.

Observe:
- WebSocket connected
- no blocked ship commands before scenario load
- no layout clipping on desktop-width browser

Logs:
- client connect
- no immediate warning or error spam

#### 0.2 Mission / Server admin sanity

Actions:
1. Open `Config > Server`.
2. Authenticate with the launch password.
3. Click `Refresh`.
4. Pause and resume simulation.
5. Set time scale to `2x`, then back to `1x`.

Observe:
- uptime cards update
- scenario/mission state appears after scenario load
- no false success messages
- auth session survives repeated refreshes

Logs:
- `RCON authenticated`
- pause/time-scale actions without errors

### Phase 1: Core Ship Binding and Helm

#### 1.1 Tutorial: Intercept and Dock

Scenario:
- `01_tutorial_intercept.yaml`

Purpose:
- active ship binding
- contact acquisition
- autopilot rendezvous
- manual override
- docking

Actions:
1. Load the scenario.
2. Confirm `_flaxosDebugState().activeShipId === "player"`.
3. Claim `captain` or `helm`.
4. Use `Ping Sensors`.
5. Lock Tycho / station contact.
6. Run `RENDEZVOUS`.
7. Disengage autopilot and apply manual throttle.
8. Re-engage and complete docking.

Observe:
- velocity changes within 10-15 seconds after manual throttle
- autopilot phase/status changes in Helm
- range closes continuously
- docking state transitions cleanly

Logs:
- scenario load
- station claim
- no disconnect or error lines during manual override

#### 1.2 Docking short-path sanity

Scenario:
- `07_docking_test.yaml`

Purpose:
- short-path docking without the long intercept burn

Actions:
1. Load the scenario.
2. Open Helm.
3. Request docking immediately.

Observe:
- docking request accepted
- `free -> approaching -> docked`

Logs:
- scenario load
- no docking-related rejection/error lines

### Phase 2: Tactical Core

#### 2.1 Combat baseline

Scenario:
- `02_combat_destroy.yaml`

Purpose:
- contacts
- target lock
- firing pipeline
- combat log

Actions:
1. Ping sensors.
2. Designate and lock the hostile contact.
3. Fire one railgun shot.
4. Change subsystem target if available.
5. Launch one torpedo if tubes are fitted.

Observe:
- lock quality and solution cards update
- fire controls react without rejection
- combat log shows a coherent shot chain
- weapons status and ammo counts change

Logs:
- no command rejection/error lines
- combat events and mission state continue updating

#### 2.2 PDC / inbound defense

Scenario:
- `26_pdc_defense.yaml`

Purpose:
- inbound threat handling
- PDC mode control
- threat board

Actions:
1. Load the scenario.
2. Set PDC to `AUTO`, then `HOLD`, then back to `AUTO`.
3. Watch inbound threat behavior.
4. Confirm threat board and combat log remain consistent.

Observe:
- PDC mode changes visibly
- inbound threat state and intercept outcomes show up
- no stale tactical panels

Logs:
- no critical errors during rapid tactical updates

### Phase 3: Engineering / Ops / Stealth

#### 3.1 Silent Running

Scenario:
- `25_silent_running.yaml`

Purpose:
- EMCON/stealth path
- cross-station command stability

Actions:
1. Claim `ops` and `comms` or switch between them.
2. Enable EMCON / stealth controls.
3. Verify sensors/comms state changes reflect the stealth posture.

Observe:
- state changes appear in ops/comms panels
- no station-switching regressions

Logs:
- scenario load
- no auth or dispatch errors while switching stations

#### 3.2 Damage Control

Scenario:
- `22_damage_control.yaml`

Purpose:
- subsystem status
- repair / damage flows

Actions:
1. Open `Ops` then `Engineering`.
2. Confirm damaged subsystems show degraded states.
3. Attempt repair/damage-control actions.

Observe:
- subsystem lists stay in sync between Ops and Engineering
- event log / status feedback changes after actions

Logs:
- subsystem/repair events, but no tracebacks

#### 3.3 Fuel Crisis

Scenario:
- `24_fuel_crisis.yaml`

Purpose:
- power/fuel/ops pressure

Actions:
1. Verify fuel state, power profile, and ship/crew panels.
2. Change power profile.
3. Watch for downstream telemetry changes.

Observe:
- power profile selector and power panels remain consistent
- no display-only dead controls

Logs:
- power or subsystem status updates without errors

### Phase 4: Science / Comms

#### 4.1 Sensor Sweep

Scenario:
- `20_sensor_sweep.yaml`

Purpose:
- science analysis flow

Actions:
1. Open `Science`.
2. Ping sensors if needed.
3. Analyze at least one contact.

Observe:
- science analysis populates usable output
- passive contacts list updates while analysis runs

Logs:
- no analysis or sensor dispatch errors

#### 4.2 Diplomatic Incident

Scenario:
- `21_diplomatic_incident.yaml`

Purpose:
- comms, incoming choices, station chat

Actions:
1. Open `Comms`.
2. Send a hail or broadcast.
3. Use the incoming choice panel if populated.

Observe:
- outgoing comms appear in UI
- incoming choices/chat do not freeze or desync

Logs:
- comms-related actions without `Unauthorized` or dispatch failures

### Phase 5: Fleet / Multi-Ship

#### 5.1 Fleet Coordination

Scenario:
- `23_fleet_coordination.yaml`

Purpose:
- fleet roster
- formation
- orders

Actions:
1. Open `Fleet`.
2. Inspect roster and tactical display.
3. Change a formation or issue orders.

Observe:
- fleet UI remains coherent under multi-ship telemetry
- no stale contacts/orders views

Logs:
- ship/fleet actions without exceptions

#### 5.2 Convoy Escort or Fleet Action

Scenarios:
- `35_convoy_escort_mp.yaml`
- `36_fleet_action_mp.yaml`

Purpose:
- stress and longer-lived combat/fleet synchronization

Actions:
1. Run one of the multi-ship scenarios.
2. Switch between `Fleet`, `Tactical`, and `Comms`.
3. Keep the scenario running for 10+ minutes.

Observe:
- no prior view corrupts the current view
- no rising reconnect churn

Logs:
- no repeated disconnects, auth churn, or error spam

### Phase 6: Mobile Pass

Use a real phone or narrow responsive mode only after the desktop pass is green.

Run this sequence:
1. `Config > Server` auth flow
2. `Tutorial: Intercept and Dock`
3. `Combat: Eliminate Threat`
4. `Damage Control`

Check:
- station selector stays usable
- mission/config layout stacks cleanly
- admin buttons remain tappable
- status bar and tabs remain legible
- no panel disappears simply because it is secondary/tertiary priority

## Mission Completion Matrix

| Layer | Scenario | Primary pass criteria |
| --- | --- | --- |
| Shell | any load | no crash, no blocked commands, auth works |
| Helm | `01_tutorial_intercept.yaml` | manual + rendezvous + docking work |
| Docking | `07_docking_test.yaml` | short-path docking succeeds |
| Tactical | `02_combat_destroy.yaml` | lock, fire, combat log all update |
| Defense | `26_pdc_defense.yaml` | PDC modes and inbound defense visible |
| Ops/Eng | `22_damage_control.yaml`, `24_fuel_crisis.yaml` | subsystem/power actions change telemetry |
| Science | `20_sensor_sweep.yaml` | contact analysis works |
| Comms | `21_diplomatic_incident.yaml` | hail/broadcast/choice flow works |
| Fleet | `23_fleet_coordination.yaml` | formation/orders remain stable |
| Stress | `35_convoy_escort_mp.yaml` or `36_fleet_action_mp.yaml` | 10+ minute multi-ship stability |

## Audit Findings to Track

These are the main refactor-era risks still worth treating as first-class UAT targets:

1. Mobile layout quality around `Config > Server`, station selection, and bridge chrome.
2. Stale docs that still describe `gui/` as the current web UI.
3. Legacy fallback UI still exists, but should be treated as compatibility-only until a deliberate retirement pass removes it.
4. The best signal for regression remains: headless station wiring smoke first, then a human mission ladder with live log monitoring.
