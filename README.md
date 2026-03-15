# Flaxos Spaceship Sim

**A hard sci-fi spaceship combat simulation. Physics-first. No HP bars. Outcomes emerge from subsystem failures, targeting pipelines, and orbital mechanics — not dice rolls.**

---

## Screenshot

```
[ screenshot placeholder — run the GUI and add one here ]
```

---

## What Is This?

Flaxos Spaceship Sim is a Python-based bridge simulation set in a hard science fiction universe. You command a warship by operating actual ship systems — sensors, helm, tactical, engineering — through a multi-crew web interface. Nothing is abstracted away. Railguns are dumb kinetic slugs that travel at 20 km/s and hit wherever physics says they'll hit. PDCs are auto-turrets that burn through ammunition. Sensors detect ships by their infrared emissions, not by some arbitrary detection radius.

Combat does not end when an HP bar reaches zero. It ends when a critical subsystem fails. Destroy an enemy's drive and they're a drifting target. Blind their sensors and they can't target you. Let your own reactor overheat and everything shuts down at once. This is *mission kill* doctrine: identify the system you need to destroy, work through the targeting pipeline, and execute.

The simulation runs as a Python TCP server that manages physics at 10Hz. A WebSocket bridge connects the server to a web-based GUI. Multiple players can each claim a different bridge station — Helm, Tactical, OPS, Engineering, Science, Comms — and operate the ship cooperatively, as a real crew would.

---

## Quick Start

### Prerequisites

- Python 3.10+
- `pip install websockets flask numpy`

### Run the full stack

```bash
cd /path/to/spaceship-sim
python tools/start_gui_stack.py
```

This starts four processes simultaneously and opens a browser tab at `http://localhost:3100/`:

| Process | Default Port |
|---------|-------------|
| TCP simulation server | 8765 |
| WebSocket bridge | 8081 |
| GUI HTTP server | 3100 |
| Asset editor | 3200 |

### Flags

```bash
# LAN multiplayer — binds to 0.0.0.0 so other machines can connect
python tools/start_gui_stack.py --lan

# Minimal mode (no station system, useful for development)
python tools/start_gui_stack.py --mode minimal

# Custom ports
python tools/start_gui_stack.py --tcp-port 9000 --ws-port 9001 --http-port 3200

# Don't open a browser automatically
python tools/start_gui_stack.py --no-browser

# Skip the asset editor server
python tools/start_gui_stack.py --no-editor
```

### Run the server only

```bash
python -m server.main                  # Station mode, localhost
python -m server.main --mode minimal   # Minimal mode
python -m server.main --lan            # LAN accessible
python -m server.main --port 9000      # Custom port
```

### Connect and play

1. Open `http://localhost:3100/` in a browser
2. The GUI connects to the WebSocket bridge automatically
3. Select a bridge station (Helm, Tactical, OPS, etc.)
4. You are on the bridge

---

## Architecture

```
Browser (GUI)
    |  WebSocket (port 8081)
    v
gui/ws_bridge.py          <-- WebSocket <-> TCP relay
    |  TCP socket (port 8765)
    v
server/main.py            <-- Server entry point, connection handler
    |
    +-- server/stations/  <-- Station manager, command routing, permissions
    |       station_types.py    (STATION_DEFINITIONS -- source of truth for station capabilities)
    |       station_manager.py  (claim/release stations, route commands to correct system)
    |
    +-- hybrid/           <-- The simulation engine
            simulator.py        (Simulator -- physics loop at 10Hz)
            ship.py             (Ship -- state container, system host)
            systems/__init__.py (system registry -- maps names to classes)
            |
            +-- systems/propulsion_system.py  (thrust, fuel, F=ma)
            +-- systems/sensors/              (passive IR detection, active radar)
            +-- systems/targeting/            (lock pipeline, firing solutions)
            +-- systems/combat/               (projectiles, torpedoes, hit location)
            +-- systems/thermal_system.py     (heat generation, Stefan-Boltzmann radiation)
            +-- systems/ecm_system.py         (jamming, chaff, flares, EMCON)
            +-- systems/cascade_manager.py    (subsystem failure propagation)
            +-- navigation/autopilot/         (autopilot program implementations)
            +-- fleet/fleet_manager.py        (multi-ship coordination)
```

### Data Flow: Command to Effect

```
Player clicks "Fire Railgun"
    |
    v
GUI: wsClient.sendShipCommand("fire_railgun", {target: "C001"})
    |
    v
ws_bridge.py: relays JSON to TCP server
    |
    v
server/main.py: parse_request() --> station dispatcher
    |
    v
station_types.py: verify TACTICAL station owns "fire_railgun"
    |
    v
hybrid/command_handler.py: route to CombatSystem.fire_railgun()
    |
    v
CombatSystem --> TargetingSystem.get_firing_solution()
                      |
                      v
                ProjectileManager.spawn_projectile()
    |
    v
Next physics tick: projectile advances, hit_location.compute_hit_location()
    |
    v
cascade_manager.py: apply cascade effects to dependent systems
    |
    v
Telemetry snapshot pushed to all connected clients
```

### Physics Tick

`Simulator` runs at `dt=0.1s` (10Hz), scalable with `--time-scale`. Each tick:

1. All ship systems call `update(dt)` — propulsion applies thrust, thermal integrates heat
2. `ProjectileManager` advances all in-flight railgun slugs
3. `TorpedoManager` updates guided torpedoes (guidance, drive burn, fuel draw)
4. Hit detection: projectile positions checked against target bounding volumes
5. Hits feed into `hit_location.compute_hit_location()` → subsystem damage → cascade effects
6. Telemetry snapshots built and pushed to subscribed clients

### Command Registration

Every server command must be registered in **three** places. Missing any one causes the command to silently fail at runtime with no error to the client:

1. `hybrid/command_handler.py` — `system_commands` dict maps command name to system and action
2. `hybrid/commands/<domain>_commands.py` — argument schema and handler function
3. `server/stations/station_types.py` — `STATION_DEFINITIONS`: command added to the owning station's `commands` set

Verify step 3 by running: `grep "my_new_command" server/stations/station_types.py`

---

## Station Guide

Up to 8 players can each claim a different station. Each station has its own permission set and filtered telemetry view.

| Station | Role | Key Commands |
|---------|------|-------------|
| **CAPTAIN** | Full command authority, can override any station | All commands |
| **HELM** | Flight control, navigation, autopilot | `set_thrust`, `set_course`, `autopilot`, `flip_and_burn`, `cold_drift`, `request_docking` |
| **TACTICAL** | Weapons, targeting, ECM | `designate_target`, `request_solution`, `fire_railgun`, `fire_pdc`, `launch_torpedo`, `deploy_chaff`, `activate_jammer` |
| **OPS** | Power management, damage control, thermal | `set_power_profile`, `allocate_power`, `dispatch_repair`, `activate_heat_sink`, `set_emcon` |
| **ENGINEERING** | Reactor, drive, repair crews | `set_reactor_output`, `throttle_drive`, `manage_radiators`, `monitor_fuel`, `emergency_vent` |
| **COMMS** | IFF transponder, radio | `set_transponder`, `hail_contact`, `broadcast_message`, `set_distress` |
| **SCIENCE** | Sensor analysis, contact classification | `ping_sensors`, `analyze_contact`, `assess_threat`, `spectral_analysis` |
| **FLEET COMMANDER** | Multi-ship coordination | `fleet_create`, `fleet_form`, `fleet_target`, `fleet_fire`, `share_contact` |

---

## Ship Classes

Five ship classes are defined in `ship_classes/` as JSON files loaded at scenario start.

| Class | Length | Dry Mass | Max Thrust | Railguns | PDCs | Torpedoes | Role |
|-------|--------|----------|-----------|---------|------|-----------|------|
| **Corvette** | 30 m | 1,200 kg | 280 N | 1 | 2 | — | Fast patrol, hit-and-run |
| **Frigate** | 50 m | 2,200 kg | 380 N | 2 | 4 | — | Multi-role workhorse |
| **Destroyer** | 80 m | 4,000 kg | 450 N | 3 | 6 | 2 | Primary fleet combatant |
| **Cruiser** | 150 m | 12,000 kg | 700 N | 4 | 8 | 3 | Capital ship, fleet command |
| **Freighter** | 120 m | 8,000 kg | 600 N | — | — | — | Cargo hauler, non-combat |

Ship mass is dynamic: `total_mass = dry_mass + fuel + ammunition`. As fuel burns and rounds fire, the ship gets lighter and acceleration increases (thrust stays constant, mass decreases — F=ma).

---

## Weapons Reference

### UNE-440 Railgun

| Parameter | Value |
|-----------|-------|
| Muzzle velocity | 20,000 m/s (20 km/s) |
| Effective range | 500 km |
| Base hull damage | 35 per hit |
| Subsystem damage | 25 per hit |
| Armor penetration | 1.5x |
| Cycle time | 5 s between shots |
| Ammo capacity | 20 rounds |
| Mass per round | 5 kg tungsten penetrator |
| Power per shot | 50 units |
| Charge time | 2 s |
| Tracking speed | 15 deg/s |
| Base accuracy | 85% at point blank |

A dumb kinetic penetrator. No guidance. Fire control calculates a lead angle based on relative velocity and fires — the round travels at 20 km/s in a straight line. At 100 km range the round takes 5 seconds to arrive. The target must be predicted, not aimed at directly.

### Narwhal-III PDC

| Parameter | Value |
|-----------|-------|
| Muzzle velocity | 3,000 m/s |
| Effective range | 5 km |
| Base hull damage | 5 per round (ablative) |
| Subsystem damage | 3 per round |
| Armor penetration | 0.5x (poor vs. armor) |
| Cycle time | 0.1 s (10 rounds/second) |
| Burst count | 5 rounds |
| Ammo capacity | 2,000 rounds |
| Mass per round | 50 g |
| Tracking speed | 120 deg/s |

Auto-turret for close-range suppression and torpedo intercept. Not effective against armored warships — poor armor penetration and light projectile mass. Primary role: shooting down incoming torpedoes before they reach attack range.

### Torpedo

| Parameter | Value |
|-----------|-------|
| Total mass | 250 kg |
| Warhead | 50 kg fragmentation |
| Thrust | 8 kN |
| ISP | 2,000 s |
| Delta-v budget | ~4,600 m/s |
| Blast radius | 100 m |
| Lethal radius | 30 m |

Guided munition with its own drive. Can maneuver to track a target. Drive plume is detectable on passive IR sensors. Interceptable by PDC — a torpedo that reaches 30 metres is lethal. Launch geometry matters: head-on with high closing speed is hardest for a PDC to engage.

---

## Game Mechanics

### Targeting Pipeline

Acquiring a firing solution is a multi-step process:

```
CONTACT --> TRACKING --> ACQUIRING --> LOCKED --> FIRING SOLUTION --> FIRE
```

1. **Contact**: Sensors detect IR or radar return. Range and bearing known.
2. **Tracking**: Tactical designates the contact. Fire control builds a track. Track quality degrades with range and target acceleration.
3. **Acquiring**: Refining track to sufficient precision for ballistic solutions.
4. **Locked**: Full fire control lock. Firing solutions are computable.
5. **Firing solution**: Lead calculation per weapon — accounts for muzzle velocity, target velocity, range, time of flight. Expressed as a confidence score.
6. **Fire**: Round or torpedo launches. Miss probability increases with range, target maneuver, and sensor damage.

Lock state **LOST** occurs if the target maneuvers aggressively, is occluded, or your sensors degrade.

### Subsystem Damage

Each ship has discrete subsystems with independent health values:

| State | Effect |
|-------|--------|
| Nominal | Full performance |
| Impaired (below failure_threshold) | Degraded performance |
| Destroyed (0%) | System offline |

Tracked subsystems: `propulsion`, `rcs`, `sensors`, `weapons`, `targeting`, `reactor`, `life_support`, `radiators`

Hit location is physics-derived. The projectile's velocity vector relative to target orientation determines which armor section is struck, angle of incidence (oblique hits may ricochet), and which subsystem is nearest the penetration point. No random hit tables.

### Cascade Effects

Subsystem failures propagate through the dependency graph:

```
reactor destroyed  --> propulsion, RCS, sensors, weapons, targeting all lose power
sensors destroyed  --> targeting lock quality degrades
rcs destroyed      --> targeting solutions degrade (cannot hold aim)
```

Cascade effects are performance penalties applied on top of direct damage — not additional damage events. A destroyed reactor denies power to everything that depends on it.

### Heat Management

Every system generates heat. Heat radiates through radiators obeying Stefan-Boltzmann law:

```
P = emissivity * sigma * area * (T^4 - T_background^4)
```

Where `sigma = 5.67e-8 W/m²/K⁴` and background temperature is 2.7 K.

| Threshold | Temperature | Effect |
|-----------|-------------|--------|
| Nominal | 300 K | Normal operation |
| Warning | 400 K | Systems throttle down |
| Emergency | 500 K | Forced shutdowns |

Radiators are exposed hardware and take damage. As radiator area shrinks, heat accumulates faster. Heat signature is also what makes ships visible on IR sensors — thermal management IS stealth management.

Heat sources:
- Reactor idle: ~20 kW continuous
- Reactor at load: up to 200 kW
- Drive: ~2% of thrust power becomes hull heat (capped at 100 kW)
- Active sensor ping: 5 kW per cycle
- Weapons: per shot

### Sensor Detection

Passive sensors detect IR emissions, not ships directly. Detection range is emission-driven: a ship thrusting at maximum produces an enormous IR signature visible at long range. A ship in cold drift (drive off, radiators minimized) has a very small signature and may only appear at close range.

Active sensors emit a radar ping with a cooldown (3–5 seconds depending on class). Active pings are themselves detectable — the enemy's science station may see when you've pinged them.

Contact confidence degrades by 20% per missed scan rather than dropping instantly. Contact IDs are stable once assigned — `C001` remains `C001` even through confidence fluctuations.

### ECM

Electronic warfare degrades enemy targeting — it does not create invisibility:

- **Radar jamming**: Noise injection reduces track quality at range. Effectiveness scales as `jammer_power / distance²`. Countered by frequency hopping.
- **Chaff**: Radar-reflective particles inflate apparent RCS, add position noise to enemy tracks. Cloud dissipates in ~30 seconds. Finite supply.
- **Flares**: 5 MW IR decoys mimicking a drive plume. Divert passive IR lock. Burn out in ~8 seconds. Finite supply.
- **EMCON**: Go passive — shut down active sensors, reduce IR signature by 70%, reduce RCS by ~30%. Limits your own detection capability.

---

## Development

### Adding a New Command

Three files must be edited. Missing any one causes silent runtime failure.

**Step 1** — `hybrid/command_handler.py`:
```python
system_commands = {
    ...
    "my_new_command": {"system": "targeting", "action": "my_new_action"},
}
```

**Step 2** — `hybrid/commands/<domain>_commands.py`:
```python
def handle_my_new_command(ship, params):
    # validate params, call system method, return result dict
    pass
```

**Step 3** — `server/stations/station_types.py`:
```python
StationType.TACTICAL: StationDefinition(
    commands={
        ...
        "my_new_command",
    },
    ...
)
```

### Adding a New Ship System

1. Create `hybrid/systems/my_system.py` inheriting from `hybrid.core.base_system.BaseSystem`
2. Implement `update(dt)`, `get_status()`, and command handlers
3. Register in `hybrid/systems/__init__.py` — add to `system_map` in `get_system_class()`
4. Add system configuration block to the relevant ship JSON or scenario file

### Adding a Ship Class

Create `ship_classes/my_class.json`. Required top-level keys: `class_id`, `class_name`, `description`, `dimensions`, `crew_complement`, `mass`, `armor`, `systems`, `weapon_mounts`, `damage_model`. Follow the existing corvette or frigate JSON as a template.

### Adding an Autopilot Program

1. Create `hybrid/navigation/autopilot/my_program.py` inheriting from `BaseAutopilot`
2. Implement `compute(dt, sim_time)` returning a command dict or `None`
3. Register in `hybrid/navigation/autopilot/factory.py` — add to `PROGRAMS` dict

---

## Testing

```bash
# Run all tests
python -m pytest tests/

# Specific module
python -m pytest tests/systems/combat/

# Smoke tests (fast sanity check)
python -m pytest tests/test_smoke.py

# Verbose
python -m pytest tests/ -v
```

Key test areas:

| Path | Covers |
|------|--------|
| `tests/test_command_registry.py` | All commands registered in all 3 required places |
| `tests/systems/combat/` | Combat system, torpedoes, hit location, damage |
| `tests/navigation/autopilot/` | Autopilot programs (intercept, orbit, evasive, rendezvous) |
| `tests/stations/` | Station permissions and command dispatch |
| `tests/protocol/` | Wire protocol v1.0 |
| `tests/utils/` | Quaternion math, JSON serialization |

---

## Project Status

### Implemented

- Newtonian flight model (F=ma, quaternion attitude, RCS torque)
- Multi-crew station system (8 stations, permission-based routing)
- Full targeting pipeline (contact → track → lock → firing solution)
- Railgun ballistics (kinetic penetrator, lead calculation)
- PDC auto-turret (burst fire, torpedo intercept mode)
- Torpedo system (guided, self-propelled, datalink updates, PDC-interceptable)
- Hit location physics (geometry-derived, no random hit tables)
- Cascade damage (reactor → downstream failures)
- Passive IR sensor model (emission-driven detection)
- Active radar with cooldown and detectable signature
- ECM (jamming, chaff, flares, EMCON)
- Thermal system (Stefan-Boltzmann radiation, overheating, forced shutdown)
- Dynamic ship mass (fuel and ammo consumption updates mass each tick)
- Autopilot programs: intercept, goto_position, match_velocity, hold, formation, orbit, evasive, rendezvous
- Fleet coordination (11 commands, 7 formation types)
- Crew fatigue system (11 skills, NOVICE–MASTER)
- 5 ship classes (corvette, frigate, destroyer, cruiser, freighter)
- Scenario system (JSON-defined ships, objectives, win/fail conditions)
- Web GUI: Helm, Tactical, OPS, Engineering, Fleet, Mission views
- Tier system (RAW / ARCADE / CPU-ASSIST complexity levels)
- Asset editor REST API

### In Progress

- Torpedo GUI integration
- Comms/IFF station UI
- Science station UI
- Fleet multiplayer UI
- Crew fatigue effects wired into combat performance
- Tutorial scenario polish

---

## Contributing

This is a solo development project by Flax. Code standards:

- Python 3.10+, type hints on all signatures, docstrings on classes and public methods
- No monolithic files — refactor at ~300 lines
- All game state changes go through the server (client is display-only)
- Commit small: one logical change per commit
- Comment WHY, not just WHAT
- Run `python -m pytest tests/` before any PR
- Verify `python -m server.main` starts cleanly
- See `CLAUDE.md` for the full development checklist

---

## License

*License TBD.*
