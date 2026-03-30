# Architecture Audit — Full System Pipeline Reference

> Generated 2026-03-30, updated after all 18 bugs resolved (PRs #264-#266).
> Updated 2026-03-29: missile pipeline, station command counts, mission progression,
> game authentication, kill confirmation, crew_fatigue telemetry.
> Use this document to troubleshoot data flow between server and GUI.

---

## Table of Contents
1. [Resolved Bugs (for reference)](#resolved-bugs)
2. [Weapons & Combat Pipeline](#weapons--combat)
3. [Sensors & Targeting Pipeline](#sensors--targeting)
4. [Navigation & Propulsion Pipeline](#navigation--propulsion)
5. [Station, Telemetry & Events Pipeline](#station-telemetry--events)
6. [Power, Engineering & Damage Pipeline](#power-engineering--damage)
7. [Mission Progression & Authentication](#mission-progression--authentication)
8. [State Manager Getter Reference](#state-manager-getters)
9. [Common Bug Patterns (avoid these)](#common-bug-patterns)

---

## Resolved Bugs

All 18 bugs identified in the original audit have been fixed. Listed here for reference to prevent regressions.

| # | Bug | Fix PR | Pattern |
|---|-----|--------|---------|
| 1 | Railgun fire param mismatch | #264 | Added `mount_id` fallback in combat_system.py |
| 2 | Cascade damage cosmetic | #264 | DamageModel auto-queries CascadeManager |
| 3 | ECM panel reads ship ID string | #264 | `getShipState()` not `getState().ship` |
| 4 | ECCM not in telemetry | #264 | Added `_get_eccm_state()` to telemetry.py |
| 5 | 15+ telemetry fields unmapped | #264 | Added display_field_mapping entries |
| 6 | Hull integrity not in telemetry | #264 | Added hull_integrity/max/percent to telemetry |
| 7 | subsystem_health key mismatch | #264 | Changed mapping from "damage_model" to "subsystem_health" |
| 8 | Thermal reads idle reactor heat | #265 | `total_output` → `total_available` |
| 9 | Throttle doesn't disengage AP | #265 | `set_thrust` routes through helm now |
| 10 | getCombat() returns null | #265 | Falls through to getWeapons() for truth_weapons |
| 11 | getPower() returns empty | #265 | Falls through to ship.ops |
| 12 | Railgun target = contact ID | #264 | Reverse ID lookup via contact tracker |
| 13 | Event filter missing categories | #265 | Synced main.py with legacy categories (31 total) |
| 14 | Dual power unsynchronized | #265 | All consumers use power_management first, PowerSystem delegates |
| 15 | Heading arrow 90 degrees off | #266 | Applied -PI/2 offset in tactical-map.js |
| 16 | Radiators missing from display | #266 | Added to SUBSYSTEM_ORDER and SUBSYSTEM_LABELS |
| 17 | Panels use wrong sendCommand | #266 | ECM/engineering use wsClient.sendShipCommand now |
| 18 | Science panel getState() bug | #264 | Uses getShipState() |

---

## Weapons & Combat

### Railgun: Full Pipeline (working)

```
CombatSystem.__init__() creates TruthWeapon(RAILGUN_SPECS, "railgun_N")
  → combat_system.py:59-65
  → Specs: truth_weapons.py:71-92 (20 km/s, 500km, 20 rounds, 5s cycle)

CombatSystem.tick() → weapon.tick(dt) → _update_weapon_solutions(ship)
  → truth_weapons.py:256-558 (lead angle, confidence cone)

GUI fire: wsClient.sendShipCommand("fire_railgun", {mount_id})
  → command_handler.py:68 → ("combat", "fire")
  → combat_system.py reads mount_id || weapon_id || weapon
  → Contact ID → ship ID reverse lookup via sensor contact tracker
  → truth_weapons.py _fire_ballistic() → projectile_manager.spawn()

Projectile flight:
  → simulator.py:259 ticks projectiles each frame
  → projectile_manager.py:177-235 swept-line hit detection (anti-tunnel at 20km/s)
  → projectile_manager.py:311-441 hit resolution → armor → subsystem damage
  → combat_log records hit/miss with causal feedback

Telemetry: get_weapons_status() → "weapons" key → truth_weapons dict
  → station_telemetry.py: TACTICAL gets "weapons"
  → stateManager.getWeapons().truth_weapons
  → weapon-controls.js _updateRailgunMounts()
  → weapons-status.js renders ammo/status/solution per mount
```

### PDC: Full Pipeline (working)

```
Auto mode: simulator.py:362-433 _process_pdc_torpedo_intercept()
  → Scans incoming torpedoes and missiles, range check, accuracy roll
  → torpedo_manager.apply_pdc_damage() on hit
  → Ammo consumed, cooldown set, heat generated

Mode toggle: wsClient.sendShipCommand("set_pdc_mode", {mode})
  → command_handler.py:86 → ("combat", "set_pdc_mode")
  → combat_system.py:511-523 — works end-to-end

PDC assignments: multi-track-panel.js reads from getWeapons().truth_weapons
  → assign_pdc_target command routes to targeting system
  → Dropdown stays open during state updates (in-place sync)
```

### Torpedo: Full Pipeline (working)

```
GUI: wsClient.sendShipCommand("launch_torpedo", {})
  → command_handler.py:87 → ("combat", "launch_torpedo")
  → combat_system.py:299-405 — contact ID → ship ID reverse lookup
  → torpedo_manager.spawn() with real ship ID and MunitionType.TORPEDO

Guidance: torpedo_manager.py:202-314
  → Proportional navigation, BOOST → MIDCOURSE → TERMINAL
  → Datalink updates from launcher sensors
  → Proximity fuse: 30m lethal, 100m blast radius

Detonation: torpedo_manager.py:460-552
  → Area damage, inverse-square falloff, fragmentation subsystem hits
  → ship.take_damage() + damage_model.apply_damage()

Combat log: torpedo_launched, torpedo_detonation, torpedo_expired, torpedo_intercepted
  → combat_log.py subscribes to all four events
  → GUI: combat-log.js TORP filter, purple styling

Telemetry: torpedo_manager.get_state() → position, velocity, state, fuel%, distance, ETA
  → station_telemetry.py:168 (TACTICAL/CAPTAIN)
  → stateManager.getTorpedoes()
  → tactical-map.js draws diamonds (green=boost, blue=midcourse, red=terminal)
  → torpedo-status.js shows distance + ETA per torpedo
```

### Missile: Full Pipeline (working)

```
Specs (torpedo_manager.py):
  Mass: 95 kg total (10kg warhead, 25kg drive, 30kg fuel, 30kg structure)
  Thrust: 10 kN → ~105 m/s² at launch mass
  Delta-v: ~6.7 km/s (17,658 m/s exhaust vel * ln(95/65))
  Warhead: 10 kg shaped charge — 30m blast radius, 10m lethal radius
  Hull damage: 25 at lethal radius; subsystem damage: 15 at lethal radius
  Flight profiles: direct, evasive, terminal_pop, bracket

GUI: weapon-controls.js TORPEDO/MISSILE toggle (launcher-type-btn)
  → wsClient.sendShipCommand("launch_missile", {profile})
  → command_handler.py → ("combat", "launch_missile")
  → combat_system.py:436 — same contact ID reverse lookup as torpedo
  → torpedo_manager.spawn() with MunitionType.MISSILE

Guidance: shares torpedo_manager.py proportional navigation
  → Profile controls midcourse behaviour only; terminal phase is same
  → Augmented PN with terminal lead correction
  → G-limit: 80G structural limit on guidance corrections

Tactical map: draws as filled triangle (vs torpedo diamond)
  → boost=orange (#ff8800), midcourse=amber (#cc8800), terminal=red-orange pulse
  → Label prefix "MSL " to distinguish from torpedoes
  → Incoming missiles get orange outline (vs red for torpedoes)

Telemetry: missiles share torpedo_manager state output; munition_type field
  → stateManager.getTorpedoes() returns both; GUI differentiates by munition_type
  → combat-log.js has MSL filter (separate from TORP filter)
  → Missile status in weapons dict: weapons.missiles.{launchers, loaded, capacity, cooldown}
```

### Kill Confirmation (working)

```
tactical-map.js tracks _previousContactIds each frame.
When a contact disappears (in previous set but not current):
  → _lastContactPositions provides last known world position
  → _explosions.push({position, startTime, duration: 2000ms})
  → _drawExplosions() renders on top of all other layers
  → Covers ship destruction AND torpedo/missile detonation disappearances
```

### Damage Pipeline (working)

```
ship.take_damage(hull_damage, source, target_subsystem)
  → ship.py:682-739
  → Reduces hull_integrity
  → 50% to targeted subsystem OR random propagation
  → Cascade effects auto-applied via DamageModel → CascadeManager
  → Publishes ship_damaged event

ship.is_destroyed() → hull_integrity <= 0
  → ship.py:864-871

simulator.py:267-271 removes destroyed ships from sim.ships dict

Mission: objectives.py:134 checks target_id not in sim.ships
  → Runs every physics tick (~10Hz)

Hull telemetry: hull_integrity, max_hull_integrity, hull_percent
  → Included in get_ship_telemetry() output
  → Mapped for OPS and ENGINEERING stations
```

---

## Sensors & Targeting

### Passive Detection (working)

```
PassiveSensor.update() — passive.py:79-180
  → IR emission model: 10MW at full burn (emission_model.py)
  → Detection range: min(physics_ir_range, hardware_cap)
  → Quality: smoothstep(distance / max(ir_range, hardware_cap))
    (quality denominator uses physics range, not hardware cap)
  → ECM flare degradation, ECCM multi-spectral filtering
  → Confidence: ratchets UP on re-detect, degrades 5% on miss
```

### Active Scanning (working)

```
ActiveSensor.ping() — active.py
  → Radar equation (1/r^4), ECM chaff/jamming, ECCM burn-through
  → Publishes sensor_ping event (reveals observer position)
  → Quality = base * ecm_jam_factor * 1.2
```

### Contact Tracking (working)

```
SensorSystem.tick() merges passive + active into ContactTracker
  → contact.py: stable IDs (C001, C002...)
  → id_mapping: {real_ship_id → contact_id}
  → get_contact() resolves by BOTH stable ID and ship ID
  → Staleness: 60s threshold, prune at 120s

IMPORTANT: Weapon systems must reverse-lookup contact IDs to ship IDs.
Pattern: walk id_mapping dict to find real_ship_id where contact_id matches.
This is implemented in combat_system.py for both torpedoes, missiles, and railgun fire.
```

### Targeting Pipeline (working)

```
designate_target(contact_id)
  → targeting_system.py: NONE → TRACKING
  → Track quality = range_factor * accel_factor * sensor_factor * ecm_factor
                     * confidence + plume_bonus
  → range_factor: power-law (1.0 - 0.7 * ratio^1.5), 0.88 at 250km, floor 0.3
  → plume_bonus: 10MW = +0.30 (additive, capped +0.60)
  → Quality >= 0.6 → ACQUIRING → lock_progress fills → LOCKED
  → _update_firing_solutions() per weapon
  → Solutions: confidence, cone_radius, hit_probability, time_of_flight

Telemetry: targeting system state → "targeting" key
  → stateManager.getTargeting()
  → targeting-display.js: 5-stage pipeline (CONTACT→TRACK→LOCK→SOLUTION→FIRE)
  → firing-solution-display.js: confidence cone, factor breakdown
```

### ECM / ECCM (working)

```
ECM (on target): ecm_system.py
  → Jamming: degrades active quality
  → Chaff: inflates RCS, position noise (active only)
  → Flares: degrades passive IR quality
  → EMCON: reduces own IR/RCS signatures

ECCM (on observer): sensors/eccm.py
  → Frequency hop: 60-80% jam reduction
  → Burn-through: 4x radar power
  → Multi-spectral: 85% chaff, 80% flare reduction
  → Home-on-jam: bearing from jammer emissions

GUI: ecm-control-panel.js reads ship.ecm via getShipState()
     eccm-control-panel.js reads ship.eccm via getShipState()
     Both use wsClient.sendShipCommand() for commands
Telemetry: ecm state at ship.ecm, eccm state at ship.eccm
  → Mapped for TACTICAL and OPS stations
```

---

## Navigation & Propulsion

### Thrust Application (working)

```
PropulsionSystem.tick() — propulsion_system.py:85
  → throttle * max_thrust = scalar force
  → Ship-frame vector (thrust, 0, 0) — +X is forward
  → quaternion.rotate_vector() to world frame
  → F=ma → ship.acceleration
  → Fuel consumed (ISP-based or proportional)
  → Mass updates via ship._update_mass()
  → Power consumed from power_management system
```

### RCS Rotation (working)

```
RCSSystem.tick() — rcs_system.py:157
  → PD attitude controller with quaternion error
  → Braking-distance rate limiting
  → Torque = I * angular_acceleration
  → Max rate 30 deg/s, overdamped
  → Power consumed from power_management system
```

### Autopilot Programs (working)

```
Factory: intercept, match_velocity, goto_position, hold_position,
         hold_velocity, formation, echelon, orbit, evasive, rendezvous, all_stop

NavigationSystem._apply_autopilot_command()
  → Throttle → propulsion.set_throttle() directly
  → Heading → helm._cmd_set_orientation_target(_from_autopilot=True)

Manual override: set_thrust routes through helm system which calls
  _record_manual_input() → disengages autopilot before forwarding to propulsion.
  set_orientation also routes through helm with same override detection.
```

### Helm Commands (all registered in 3 places)

```
set_thrust, set_orientation, set_course, autopilot, execute_burn,
plot_intercept, flip_and_burn, emergency_burn, emergency_stop,
take_manual_control, release_to_autopilot, get_nav_solutions
```

### Tactical Map (working)

```
Coordinate system: X-Z plane top-down (Y ignored)
  → Screen X = world X (right positive)
  → Screen Y = -world Z (up positive on screen = +Z in world)
  → Heading arrow: yaw rotation - PI/2 (compensates yaw=0 means +X)

Contact rendering: IFF shapes (diamond=friendly, square=hostile, circle=unknown)
  → Confidence scales alpha, error ellipses for confidence < 0.8
  → Auto-fit scale: 8 levels from 1km to 1000km radius

Projectiles: bright dots with velocity trails, colored by weapon type
Torpedoes: diamonds colored by phase (green/blue/red), with target links
Missiles: triangles colored by phase (orange/amber/red-orange), labeled "MSL"
```

---

## Station, Telemetry & Events

### Stations

Command counts are taken directly from `server/stations/station_types.py` `STATION_DEFINITIONS`.

| Station | Command Count | Key Systems |
|---------|--------------|-------------|
| CAPTAIN | all (union) | everything |
| HELM | 34 | propulsion, helm, navigation |
| TACTICAL | 45 | weapons, targeting, ECM/ECCM |
| OPS | 27 | power, power_management, crew |
| ENGINEERING | 21 | power, propulsion, engineering |
| COMMS | 11 | comms |
| SCIENCE | 9 | sensors |
| FLEET_COMMANDER | 12 | comms |

### Mission Loading (captain-gated)

```
First client: auto-assigned CAPTAIN, can load any scenario
Additional clients: join via fleet lobby at vacant stations
Solo client: can always reload (bypasses captain check)
Multi-client: only CAPTAIN can reload; stale claims purged on reload
```

### Telemetry Paths

```
Path A (snapshot): get_telemetry_snapshot() → all ships + projectiles + torpedoes
  → Used when get_state has NO ship param

Path B (per-ship): get_ship_telemetry(ship) → 40+ top-level keys
  → Used when get_state has ship param (GUI's normal path)
  → Filtered by filter_ship_telemetry() for non-CAPTAIN stations
  → Torpedoes and projectiles appended for TACTICAL/CAPTAIN

GUI polls Path B: stateManager._fetchState() sends {cmd:"get_state", ship:playerShipId}
```

### Telemetry Fields (all mapped)

Top-level keys in get_ship_telemetry():
```
position, velocity, velocity_magnitude, acceleration, orientation, angular_velocity,
fuel, delta_v_remaining, ponr, trajectory, nav_mode, autopilot_program,
autopilot_state, course, helm_queue, flight_computer, weapons, ammo_mass,
sensors, emissions, thermal, ops, ecm, eccm, engineering, comms, docking,
subsystem_health, cascade_effects, hull_integrity, max_hull_integrity,
hull_percent, armor_status, systems
```

display_field_mapping covers all of these for appropriate stations:
- HELM: nav_status, fuel_status, autopilot_status, helm_status (+ponr, trajectory, flight_computer)
- TACTICAL: weapons_status, firing_solution, sensor_contacts, ecm_status, emissions_status, engagement_envelope, damage_assessment
- OPS: sensor_contacts, thermal_status, heat_status, subsystem_health (+cascade_effects), ops_status, power_management_status, crew_fatigue_status
- ENGINEERING: engineering_status, thermal_status, heat_status, subsystem_health (+cascade_effects), hull_integrity
- COMMS: comms_status, comm_log
- SCIENCE: sensor_contacts, contact_detail

Note: `crew_fatigue_status` is listed in `station_types.py` displays for OPS and ENGINEERING but the corresponding telemetry field is pending addition to `hybrid/telemetry.py`. Until that is done, OPS/ENGINEERING will not receive crew fatigue data through the filtered telemetry path.

### Event System (31 categories)

```
EventBus.publish() → Simulator._record_event() → EventLogBuffer (1000 max)
  → Client polls get_events every 500ms
  → _filter_events_for_station() filters by 31 categories:

HELM: autopilot, navigation, propulsion, course, docking
TACTICAL: weapon, target, fire, pdc, torpedo, threat
OPS: sensor, contact, detection, ping, ecm, signature, crew
ENGINEERING: power, reactor, damage, repair, system, fuel, engineering
COMMS: comm, fleet, hail, message, iff
FLEET_COMMANDER: fleet_tactical, fleet_formation, fleet_status, engagement
ALL STATIONS: critical, alert, mission, mission_update, mission_complete, hint, gimbal_lock
```

### Command Registration (3-place requirement)

```
1. hybrid/command_handler.py — system_commands dict
2. hybrid/commands/*.py — command spec with args/handler
3. server/stations/station_types.py — station permissions

Lint: hybrid/command_registry_lint.py — 127 handlers, 128 station, 0 errors
```

---

## Power, Engineering & Damage

### Power System (unified lookup)

```
PowerManagementSystem (power/management.py): Primary system
  → Multi-reactor model (primary/secondary/tertiary)
  → Per-layer thermal limits, engineering profiles
  → draw_power(), overdrive
  → Registered as "power_management" in systems registry

PowerSystem (power_system.py): Legacy fallback
  → Delegates to PowerManagementSystem when both exist
  → No ship config currently creates this system

All consumers use consistent lookup:
  systems.get("power_management") or systems.get("power")
  → propulsion, RCS, helm, bio_monitor, combat, weapons, sensors
```

### Heat System (two-tier, working)

```
Per-subsystem: damage_model.add_heat() → SubsystemHealth.heat
  → Overheat penalty: weapons 0.0 (can't fire), propulsion 0.6

Ship-wide: ThermalSystem (thermal_system.py)
  → Stefan-Boltzmann radiative cooling
  → Sources: reactor waste (scales with total_available), drive waste,
    subsystem heat, active sensors
  → Emergency shutdown on critical hull temperature
```

### Cascade Manager (working — has gameplay effect)

```
Dependencies (cascade_manager.py):
  reactor → propulsion, rcs, sensors, weapons, targeting, life_support, radiators
  sensors → targeting
  rcs → targeting

DamageModel.get_combined_factor() auto-queries CascadeManager:
  → If cascade_manager attached, factor = damage * heat * cascade
  → No explicit cascade_factor needed at call sites
  → Destroyed reactor = propulsion/weapons/sensors degraded to 0
  → 14 integration tests verify cascade behavior
```

### Armor Model (working)

```
ArmorModel (combat/armor.py): Per-section tracking
  → fore, aft, port, starboard, dorsal, ventral
  → Material resistance, ablation rates
  → Ricochet above 70 degrees
  → PDC slowly strips armor, railguns punch or ricochet
  → Mutable state: repeated hits degrade section thickness
```

### Ship Destruction (working)

```
ship.take_damage() → hull_integrity -= damage → ship.py:682
ship.is_destroyed() → hull_integrity <= 0 → ship.py:864
simulator.py:267-271 removes from sim.ships dict
objectives.py:139 checks target_id not in sim.ships
```

---

## Mission Progression & Authentication

### Mission Progression

```
Scenario YAML: next_scenario field links to the next scenario ID
  → scenarios/01_tutorial_intercept.yaml → next_scenario: "02_combat_destroy"
  → scenarios/02_combat_destroy.yaml    → next_scenario: "03_escort_protect"

hybrid_runner.py:105-107: includes next_scenario in mission status dict
  → hybrid/scenarios/loader.py reads next_scenario from YAML
  → hybrid/scenarios/mission.py stores it on the Mission object

GUI (gui/js/main.js):
  → Polls get_mission on mission_complete events to capture next_scenario
  → app.nextScenarioId stores it across the session
  → Mission completion overlay: shows NEXT MISSION button if nextScenarioId is set
  → State machine: lobby → playing → ended (overlay shown on ended)
```

### Game Authentication

```
--game-code flag: passed to ws_bridge.py at startup via start_gui_stack.py
  → gui/ws_bridge.py:196 stores game_code on the WsBridge instance
  → When game_code is set, the first WS message from every new client
    MUST be {type: "auth", code: <game_code>}
  → Invalid or missing code: connection closed with auth error
  → No game_code configured: auth check is a no-op (open access)

URL parameter: ?game_code=XXXX in the browser URL
  → gui/js/ws-client.js:449 reads it on bootstrap
  → Sent as the auth message before any other commands

Affected files:
  → gui/ws_bridge.py (WsBridge._authenticate_client, _handle_client_connection)
  → gui/js/ws-client.js (bootstrap, first-message auth)
  → tools/start_gui_stack.py (--game-code arg forwarded to ws_bridge)
```

---

## State Manager Getters

All getters use `typeof === "object"` guards to avoid the status-string trap.

| Method | Reads From | Notes |
|--------|-----------|-------|
| `getShipState()` | `state.state` or `state.ships[id]` | Primary ship telemetry accessor |
| `getContacts()` | `ship.sensors.contacts` | Array of contact objects |
| `getSensors()` | `ship.sensors` (typeof guard) | Full sensor state |
| `getTargeting()` | `ship.targeting` | Lock state, solutions |
| `getWeapons()` | `ship.weapons` (typeof guard) | truth_weapons, torpedoes, missiles, pdc_mode |
| `getCombat()` | Falls through to `getWeapons()` when it has truth_weapons | No separate `combat` telemetry key |
| `getThermal()` | `ship.thermal` | Hull temp, radiators |
| `getNavigation()` | Assembled from ship position/velocity/heading | Composite getter |
| `getSystems()` | `ship.systems` | Returns **status strings only** — never use for data |
| `getProjectiles()` | `state.projectiles` | TACTICAL/CAPTAIN only |
| `getTorpedoes()` | `state.torpedoes` | TACTICAL/CAPTAIN only; includes missiles (differentiate by munition_type) |
| `getPower()` | Falls through to `ship.ops` | No separate `power` telemetry key |

---

## Common Bug Patterns

These patterns caused most of the 18 bugs. Check for them in any new code.

### 1. Status string vs data object
`ship.systems.X` returns a **status string** like `"online"`, not the system data object.
The real data is at `ship.X` (e.g., `ship.weapons`, `ship.ecm`, `ship.sensors`).
Always use `typeof === "object"` guard before trusting `systems.*` values.

### 2. getState() vs getShipState()
`stateManager.getState()` returns the raw response where `.ship` is a **ship ID string**.
`stateManager.getShipState()` returns the actual **telemetry object**.
Always use `getShipState()` in GUI components.

### 3. Contact ID vs ship ID
The targeting system uses stable contact IDs (`"C001"`). The simulator uses real ship IDs (`"pirate01"`).
Any weapon fire or damage code must **reverse-lookup** the contact ID via the sensor contact tracker's
`id_mapping` dict to get the real ship ID before looking up in `sim.ships`.

### 4. Telemetry field mapping
New telemetry fields must be added to `display_field_mapping` in `station_telemetry.py`,
otherwise non-CAPTAIN stations won't receive them. Also add the display name to the
station's `displays` set in `station_types.py`.

### 5. sendShipCommand vs send
Ship-scoped commands: `wsClient.sendShipCommand(cmd, args)` — auto-injects ship ID.
Meta commands (get_mission, list_scenarios): `wsClient.send(cmd, args)` — no ship ID.

### 6. station_server.py is dead code
`server/station_server.py` is DELETED. The production server is `server/main.py` (`UnifiedServer`).
Any fix applied to `station_server.py` has no effect. Always edit `server/main.py`.

### 7. Target resolution in ship systems
Use `ship._all_ships_ref` for looking up other ships by ID inside ship-scoped system code.
Do not use `params.get('all_ships')` — that dict is not reliably passed through all call paths.
`hybrid_runner.py` sets `_all_ships_ref` on every ship each tick.

---

## Key File Reference

### Server Core
- `server/main.py` — ONLY entry point and command dispatch (UnifiedServer), event filtering (31 categories)
- `server/stations/station_types.py` — Station definitions and permissions (source of truth for command counts)
- `server/stations/station_manager.py` — Session/claim management, purge stale claims
- `server/stations/station_telemetry.py` — Telemetry filtering per station (display_field_mapping)
- `hybrid_runner.py` — Simulation runner, scenario loading, mission tracking, sets ship._all_ships_ref

### Game Systems
- `hybrid/ship.py` — Ship model, physics integration, take_damage, cascade wiring
- `hybrid/simulator.py` — Tick loop, projectile/torpedo ticking, PDC intercept, destruction
- `hybrid/telemetry.py` — Telemetry serialization (40+ fields including ecm, eccm, hull)
- `hybrid/command_handler.py` — system_commands routing dict (set_thrust → helm)
- `hybrid/systems/combat/combat_system.py` — Railgun/PDC/torpedo/missile, contact ID reverse lookup
- `hybrid/systems/combat/torpedo_manager.py` — Torpedo and missile guidance, detonation, distance/ETA
- `hybrid/systems/combat/projectile_manager.py` — Ballistic projectile simulation
- `hybrid/systems/combat/combat_log.py` — Combat event logging (torpedo and missile events subscribed)
- `hybrid/systems/targeting/targeting_system.py` — Lock pipeline, firing solutions, plume bonus
- `hybrid/systems/targeting/multi_track.py` — Multi-target tracking, bandwidth penalty
- `hybrid/systems/sensors/passive.py` — IR detection (quality uses physics range)
- `hybrid/systems/sensors/active.py` — Radar scanning
- `hybrid/systems/sensors/contact.py` — Contact tracker, stable IDs, id_mapping
- `hybrid/systems/sensors/eccm.py` — Electronic counter-countermeasures
- `hybrid/systems/ecm_system.py` — Jamming, chaff, flares
- `hybrid/systems/propulsion_system.py` — Thrust, fuel, ISP, power_management lookup
- `hybrid/systems/rcs_system.py` — Torque-based rotation, power_management lookup
- `hybrid/systems/damage_model.py` — Subsystem health, heat, auto-cascade integration
- `hybrid/systems/cascade_manager.py` — Damage dependency cascades (reactor→everything)
- `hybrid/systems/thermal_system.py` — Ship-wide heat (reads total_available from reactor)
- `hybrid/systems/power_system.py` — Legacy power model (delegates to PowerManagement)
- `hybrid/systems/power/management.py` — Multi-reactor power model (primary system)
- `hybrid/combat/armor.py` — Per-section armor ablation
- `hybrid/navigation/navigation_controller.py` — Manual/autopilot modes
- `hybrid/navigation/autopilot/` — 11 autopilot programs
- `hybrid/scenarios/objectives.py` — Mission win/loss conditions (14 types)
- `hybrid/scenarios/loader.py` — Reads next_scenario from YAML
- `hybrid/scenarios/mission.py` — Mission object, stores next_scenario

### GUI
- `gui/js/main.js` — Component registration, app init, mission progression overlay, NEXT MISSION button
- `gui/js/state-manager.js` — Telemetry state store and getters (typeof guards)
- `gui/js/ws-client.js` — WebSocket client, sendShipCommand, game_code auth bootstrap
- `gui/ws_bridge.py` — WS↔TCP bridge (per-client TCP connections, reconnection, game_code auth)
- `gui/components/weapon-controls.js` — Fire buttons (railgun/torpedo/missile), PDC mode toggle, launcher type toggle
- `gui/components/weapons-status.js` — Weapon mount display (reads getWeapons())
- `gui/components/torpedo-status.js` — Active torpedo/missile tracking (distance, ETA)
- `gui/components/firing-solution-display.js` — Confidence cone, factor breakdown
- `gui/components/targeting-display.js` — 5-stage lock pipeline
- `gui/components/tactical-map.js` — Top-down map (heading offset corrected, kill confirmation explosions)
- `gui/components/sensor-contacts.js` — Contact list
- `gui/components/multi-track-panel.js` — Multi-target + PDC assignments (in-place select sync)
- `gui/components/ecm-control-panel.js` — ECM controls (reads ship.ecm, uses sendShipCommand)
- `gui/components/eccm-control-panel.js` — ECCM controls (reads ship.eccm, uses sendShipCommand)
- `gui/components/subsystem-status.js` — Damage display (includes radiators)
- `gui/components/combat-log.js` — Combat event feed (TORP and MSL filters)
- `gui/components/flight-data-panel.js` — Nav/fuel data
- `gui/components/manual-flight-panel.js` — Throttle/heading controls
- `gui/components/flight-computer-panel.js` — Autopilot commands
- `gui/components/engineering-control-panel.js` — Engineering (uses sendShipCommand)
- `gui/components/science-analysis-panel.js` — Science (uses getShipState())
- `gui/components/comms-control-panel.js` — Comms (uses getShipState().comms)
- `gui/components/scenario-loader.js` — Mission select / fleet lobby (captain-gated)
