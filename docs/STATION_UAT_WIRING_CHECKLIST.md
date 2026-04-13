# Station UAT Wiring Checklist

This checklist is for resuming UI UAT after station refactors. It is focused on
deterministic bridge wiring, not balance tuning.

Use it to answer three questions in order:

1. Did the scenario load the correct ship with the correct systems?
2. Did the client bind to the active player ship and station?
3. Did the command produce the expected telemetry change?

## Preflight

1. Start the stack in station mode.
   `python3 tools/start_gui_stack.py --mode station --browser --rcon-password 'replace-this'`
2. Open the Svelte GUI.
3. Open browser devtools and run:
   `_flaxosDebugState()`
4. Load a scenario, then open `Config > Server` and authenticate with the same RCON password.

Expected before starting a mission:
- `ws.isConnected` is `true`
- `activeShipId` is `null`
- `blockedCommandTotal` is `0`

Expected after authenticating in `Config > Server`:
- server uptime is visible
- mission uptime becomes non-`n/a` after loading a mission
- scenario name, pause state, sim time, and time scale refresh without reloading the page

## Fast Headless Smoke

Run this before UI UAT:

```bash
python3 tools/check_station_wiring.py
```

Expected:
- `PASS loadout`
- `PASS manual`
- `PASS auto`
- `PASS overall`

If this fails, stop and fix backend/scenario wiring first. UI UAT will not be trustworthy.

## Admin Panel Sanity

Run this once before the station-specific flows:

1. In `Config > Server`, click `Refresh`.
2. Toggle `Pause Simulation`, then resume.
3. Set time scale to `2x`, then back to `1x`.

Expected:
- No generic success/failure mismatch in the UI
- Pause state and time scale change immediately in the status card
- No stale auth session or `Unauthorized` error while the server is still running

## Tutorial 01: Helm Manual + Rendezvous

Scenario:
- `01_tutorial_intercept.yaml`

Purpose:
- validate mission load
- validate active ship binding
- validate manual thrust
- validate lock + rendezvous autopilot
- validate docking flow

Steps:
1. Load `Tutorial: Intercept and Dock`.
2. Run `_flaxosDebugState()`.
3. Confirm:
   - `activeShipId === "player"`
   - `shipStateId === "player"`
   - `blockedCommandTotal === 0`
4. Switch to Helm.
5. Use `Ping Sensors`.
6. Lock the station contact.
7. In `Flight Computer`, click `RENDEZVOUS`.
8. Watch `FlightDataPanel` and `AutopilotStatus`.
9. When inside 5 km, use `DockingPanel` to request docking.

Expected:
- No generic `Command rejected` message
- `AutopilotStatus` shows an active program and phase
- Speed increases above `100 m/s` within roughly 10-15 seconds
- Range to target trends downward
- Docking request succeeds inside range/velocity limits

Manual override check:
1. Disengage autopilot.
2. In `ManualFlightPanel`, set throttle to `25%`.
3. Wait 3-5 seconds.

Expected:
- Velocity magnitude increases
- No blocked ship commands in `_flaxosDebugState().ws.blockedCommands`

## Tutorial 07: Close Docking Sanity

Scenario:
- `07_docking_test.yaml`

Purpose:
- short-range docking validation without a long approach burn

Steps:
1. Load the scenario.
2. Confirm `_flaxosDebugState()` still reports the correct ship.
3. Request docking from the docking panel.

Expected:
- Docking state transitions: `free -> approaching -> docked`

## Tutorial 02: Tactical Basic Fire

Scenario:
- `02_combat_destroy.yaml`

Purpose:
- validate contact lock
- validate tactical fire controls
- validate combat telemetry and log feedback

Steps:
1. Load the scenario.
2. Ping sensors.
3. Lock the hostile contact.
4. Fire one railgun shot.
5. If available, launch one missile or torpedo.

Expected:
- Lock quality and solution update in tactical panels
- Fire buttons send commands without rejection
- Combat log records the shot/event chain

## MANUAL Tier Pass

Run these in `manual` tier:
- Tutorial 01: manual throttle, pitch/yaw/roll, then rendezvous
- Tutorial 02: lock target, fire individual weapons, review combat log
- Tutorial 07: docking request and undock

Expected:
- keyboard/manual controls change telemetry
- per-panel commands change the correct subsystem state
- no hidden auto-assist is required for success

## RAW Tier Pass

Run these in `raw` tier:
- Tutorial 01: inspect vectors, heading, delta-v, queue, and exact autopilot data
- Tutorial 02: inspect firing factors, lock pipeline, subsystem targeting
- Engineering/Ops: verify exact power and repair telemetry values appear

Expected:
- raw numeric views update continuously
- no panel is display-only unless intended by tier rules

## Failure Triage

If a panel appears wired but nothing happens:

1. Check `_flaxosDebugState()`.
   - `activeShipId` missing means the GUI is not bound to a ship.
   - `blockedCommandTotal > 0` means ship commands were sent before the active ship was set.
2. Check the panel feedback text.
   - The UI should now surface server rejection reasons instead of only `Command rejected`.
3. Run:
   `python3 tools/check_station_wiring.py`
4. If headless passes but GUI fails, the issue is client binding or view wiring.
5. If headless fails, the issue is scenario/backend command flow.
6. If `Config > Server` shows success but uptime/state does not change, treat it as a backend admin-command regression and stop UAT.
