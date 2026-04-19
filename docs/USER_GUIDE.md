# User Guide (Player)

The default supported interface is the **v3 browser bridge UI** served from `gui-svelte/`.

## Startup

```bash
python3 tools/start_gui_stack.py --browser --rcon-password 'replace-this'
```

Open the browser UI, load a scenario from `Mission`, then claim a station.

## Main Views

- `Helm`: flight computer, manual flight, docking, queue, navigation awareness
- `Tactical`: contacts, lock pipeline, weapons, ECM/ECCM, combat log
- `Engineering`: thermal, drive, power, subsystems
- `Ops`: damage control, power profile, crew, boarding, drones
- `Science`: passive contacts and analysis
- `Comms`: radio, incoming choices, station chat
- `Fleet`: formation, orders, shared contacts, fleet fire control
- `Mission`: scenario loader, objectives, campaign, command console, server admin

## Core Flow

1. Load a scenario from `Mission`.
2. Claim a station.
3. Use the relevant station panels for that role.
4. For repeatable UAT or multiplayer triage, authenticate in `Mission > Server`.

## Current Supported Controls

- Use the contacts panels to select and lock targets.
- Use the flight computer for intercept/rendezvous/match/hold programs.
- Use tactical controls for railgun, PDC, launcher, and subsystem targeting.
- Use `Mission > Server` for pause/resume, time scale, mission reset, server reset, and client management.

## UAT Tip

For repeatable UAT:

```bash
python3 tools/start_gui_stack.py --browser --rcon-password 'replace-this'
python3 tools/check_station_wiring.py
python3 tools/uat_monitor.py --follow --fail-on-critical
```

## Historical Controls

The old desktop-control reference remains historical only:
- Click a contact to select a target
- `F` fire
- `P` ping sensors
- `A` toggle autopilot override
- `R` record replay output
