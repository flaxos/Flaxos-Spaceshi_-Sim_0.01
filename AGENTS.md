# Project Overview
Flaxos Spaceship Sim is a modular 3D spaceflight simulator with a tactical
command layer. Ships simulate real-world movement, system loadouts, and power
management in physical units (`kW`), while the default player interface is the
Svelte bridge UI served over a WebSocket bridge.

This file is for AI agents working in the repo. Prefer the current entrypoints
and file paths below over older references in historical notes or archived docs.

## Current Stack Notes
- Use `python -m server.main` as the canonical TCP server entrypoint.
- Use `python tools/start_gui_stack.py` to launch the full browser stack.
- The default frontend is `gui-svelte/`; `gui/` is the legacy fallback UI.
- Remote admin and UAT controls live in `Mission > Server` and are backed by
  RCON-style commands exposed through the WebSocket bridge.

## Key Files and Roles

| File | Purpose |
|------|---------|
| `server/main.py` | Canonical TCP server entrypoint; station mode, minimal mode, RCON/admin |
| `hybrid/simulator.py` | Main simulation loop ticking all ships |
| `hybrid/ship.py` | Ship-local command handlers, including power commands |
| `hybrid/command_handler.py` | Command routing from server commands into ship systems |
| `hybrid/ship_factory.py` | Instantiates ship systems from configuration |
| `hybrid/systems/power/management.py` | Reactors, buses, batteries, profiles, and draw reporting |
| `server/stations/station_commands.py` | Station-safe wrappers for gameplay and power commands |
| `gui/ws_bridge.py` | Browser WebSocket bridge, auth gate, and origin checks |
| `tools/start_gui_stack.py` | Full-stack launcher for TCP server + WS bridge + frontend |
| `gui-svelte/src/views/MissionView.svelte` | Mission tab wiring, including the Server panel |
| `gui-svelte/src/components/mission/ServerAdminPanel.svelte` | Admin/UAT UI for RCON-backed server actions |

## Power Management System

### Structure
- `Reactor` ramps output over time:
  - States: `COLD -> SPOOLING_UP -> READY`
  - Max output in `kW`
  - Ramp rate = `max_output / 10` per tick
- `PowerBus` types:
  - `primary`: propulsion, railgun, active sensors
  - `secondary`: RCS, PDC, drones, comms
  - `tertiary`: life support, nav computer, bio monitor
- `Battery` buffers secondary-bus demand and charging
- `PowerManagementSystem`:
  - receives reactor output
  - allocates by `power_allocation`
  - tracks draw, supply, enabled systems, and profiles
  - serves `get_draw_profile()` for UI and telemetry consumers

### Tick Integration
The simulator tick loop already calls `tick()` on each system inside `Ship.tick()`.
Callers should not manually tick the power system out-of-band.

## Power Command Surface
- Ship-local handlers live in `hybrid/ship.py` (`get_power_state`,
  `set_power_allocation`, `set_power_profile`, `get_power_profiles`).
- Station-safe wrappers live in `server/stations/station_commands.py`.
- Remote/browser clients should use JSON commands over TCP/WS, for example:

```json
{"cmd": "get_power_state"}
{"cmd": "set_power_profile", "profile": "offensive"}
{"cmd": "get_power_profiles"}
{"cmd": "set_power_allocation", "allocation": {"primary": 0.5, "secondary": 0.3, "tertiary": 0.2}}
{"cmd": "get_draw_profile"}
```

## Agent Notes
- Units are kinetic (`kW`) for draw and supply. Only bus allocation uses ratios.
- All systems expose `.enabled` and `power_draw` style state; do not hardcode bus
  or system names when schema/config should be the source of truth.
- GUI, station commands, and ship-local handlers should reuse the same internal
  power-management logic rather than forking behavior per client.
- For frontend work, prefer the Svelte implementation in `gui-svelte/`.
- For remote-admin work, remember that RCON password rotation is runtime-only
  unless startup config or launch docs are also updated.

## Current Gaps / Follow-Ups
- Power UX can still be improved with better engineering visualizations and
  clearer failure-mode surfacing.
- Auto-shutdown and deeper reactor wear/overheat modeling remain optional future work.
- Keep smoke/UAT coverage aligned with the default Svelte UI, not just legacy DOM flows.
