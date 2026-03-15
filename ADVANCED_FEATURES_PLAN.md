# Advanced Features Development Plan

**Project**: Flaxos Spaceship Simulator
**Date**: 2026-03-14
**Branch**: automaker-systems-overhaul
**Horizon**: 3–6 months of post-overhaul development

---

## Current State Summary

The `automaker-systems-overhaul` branch delivered a large suite of new systems on top of the
original physics and station architecture. The following are confirmed implemented and present
in the codebase:

**Physics and navigation:** Newtonian Epstein-style propulsion, quaternion attitude integration,
RCS torque model, autopilot programs (intercept, rendezvous, goto, orbit, evasive), delta-v /
Tsiolkovsky fuel budget, relative motion and CPA calculations.

**Sensors:** Passive IR detection with range-scaled emission model, active radar ping, contact
tracker with stable IDs and confidence degradation, maneuvering IR signature tradeoff (drive
burn scales IR signature; cold-drift mode cuts signature at the cost of weapons and active
sensors), ECM (jammer, chaff, flares, EMCON), firing solution confidence scoring.

**Combat:** Truth weapons (railgun, PDC), torpedo system with proportional-navigation guidance,
projectile manager with ballistic intercept checks, PDC auto-interception of torpedoes, hit
location physics, damage cascade (subsystem health levels: nominal/impaired/destroyed with
criticality and cascade effects), combat log with causal chain narratives.

**Ship systems:** Thermal system with drive heat, radiator management, and cold-drift mode;
power management with layered reactors; crew fatigue and g-load impairment model; engineering
system for repair prioritization; ops system; science station (sensor analysis, mass estimation,
threat assessment); comms and IFF system; fleet coordination with formation types and coordinated
fire; modular ship definitions with JSON class templates (corvette, frigate, destroyer, cruiser,
freighter).

**Infrastructure:** EventBus pub/sub, station architecture with 7 crew roles and permission levels,
hybrid command handler with three-place registration requirement, WebSocket bridge and web GUI,
5 YAML scenarios with objective tracking, test suite with ~200 test files.

**What this plan covers:** The next phase of work — what to build once the current overhaul
branch is merged and stable. Organized by priority tier, from immediate hardening to long-horizon
scale work.

---

## How to Read This Document

Each feature entry follows this format:

- **What it does** — functional description
- **Why it matters** — design/gameplay justification grounded in the hard sci-fi principles
- **Key files affected** — where the work lives
- **Estimated complexity** — small (hours to 1 day), medium (2–5 days), large (1–3 weeks)
- **Dependencies** — what must be merged or completed first

Estimated complexity is for a single focused developer. It does not account for agent-assisted
parallel work.

---

## Tier 1: Hardening and Polish (1–2 weeks)

The overhaul branch added many systems quickly. Before building on top of them, the foundations
need to be solid. These items are blockers for everything in Tier 2.

---

### 1.1 File Size Refactoring

**What it does:** Splits three files that exceed the 300-line ceiling defined in CLAUDE.md into
smaller, single-responsibility modules.

- `hybrid/systems/helm_system.py` (1,235 lines reported) — split into
  `helm_control.py` (authority model, throttle routing), `helm_queue.py` (command queue),
  and `helm_autopilot_bridge.py` (autopilot handoff logic).
- `hybrid/systems/weapons/truth_weapons.py` (1,174 lines reported) — split into
  `weapon_specs.py` (dataclasses and enums), `railgun.py` (railgun-specific logic),
  and `pdc.py` (PDC-specific logic).
- `hybrid/ship.py` (1,056 lines reported) — split into `ship_core.py` (tick, state),
  `ship_damage.py` (damage model delegation), and `ship_telemetry.py` (telemetry helpers).

**Why it matters:** Files over 300 lines are hard to reason about, cause merge conflicts, and
make it impossible to isolate tests. The command registration requirement becomes fragile when
routing logic is buried in a 1,200-line file.

**Key files affected:** `hybrid/systems/helm_system.py`, `hybrid/systems/weapons/truth_weapons.py`,
`hybrid/ship.py`, plus any importer of these modules (check with grep before splitting).

**Estimated complexity:** Medium per file. Large in aggregate because import chains need auditing.

**Dependencies:** None. Can start immediately after merge.

---

### 1.2 PDC Balance Fixes

**What it does:** Adjusts two PDC parameters that are out of balance:

1. Heat per burst: reduce from current value to 0.5–1.0 units per round so sustained PDC
   fire does not overheat the weapon after a single engagement.
2. Fragmentation damage floor: add a minimum penetration value so PDC rounds cannot do
   literally zero subsystem damage through heavy armor (they should still be ineffective,
   but not completely nullified).

**Why it matters:** PDC is the primary point-defense tool and the main anti-torpedo layer. If
it overheats in the first torpedo wave, it becomes useless precisely when the player needs it
most. The design intent is that PDC ablates and suppresses, not that it dies in 10 rounds.

**Key files affected:** `hybrid/systems/weapons/truth_weapons.py` (`PDC_SPECS` dataclass),
`hybrid/systems/combat/combat_system.py` (heat application per burst).

**Estimated complexity:** Small.

**Dependencies:** 1.1 (file split) recommended first so the edit target is smaller.

---

### 1.3 ECM Balance: Steeper Distance Falloff

**What it does:** Adjusts the ECM jammer effectiveness formula to use a steeper inverse-square
falloff, so jamming at 50 km is dramatically less effective than jamming at 5 km. Currently
jamming is too universally effective regardless of geometry.

**Why it matters:** Hard sci-fi ECM should be range-constrained. A jammer powerful enough to
degrade targeting at 100 km would be visible to every sensor in the system. The tactical choice
should be: close range for better jamming effect vs. close range making you targetable. If
jamming works at all ranges equally, there is no tradeoff.

**Key files affected:** `hybrid/systems/ecm_system.py` (`_calc_jammer_effectiveness` or
equivalent method), `hybrid/systems/sensors/passive.py` (where jammer effect is applied
to detection probability).

**Estimated complexity:** Small.

**Dependencies:** None.

---

### 1.4 Crew Fatigue: High-G Impairment Wired to Combat Actions

**What it does:** Connects the existing `CrewFatigueSystem` g-load impairment calculations
to actual in-game outcomes. Currently the system tracks fatigue and g-load correctly but the
impairment multipliers are not applied to weapon firing accuracy, targeting lock time, or
manual helm response rate.

Specifically:
- At g > 5.0: targeting lock time increases by `1 / performance_multiplier`
- At g > 5.0: railgun firing solution confidence is penalized by the same factor
- At g > 7.0 sustained: blackout flag disables manual commands until recovery

**Why it matters:** This is the physics-grounded equivalent of "pilot skill." A pilot pulling
7g in a hard burn cannot hold a firing solution with the same precision as one at 1g. Without
this connection, the crew fatigue system is bookkeeping with no gameplay effect.

**Key files affected:** `hybrid/systems/crew_fatigue_system.py` (expose impairment factor),
`hybrid/systems/targeting/targeting_system.py` (apply impairment to lock time and confidence),
`hybrid/systems/helm_system.py` (apply blackout check to manual commands).

**Estimated complexity:** Medium.

**Dependencies:** None.

---

### 1.5 Combat Log: Wire Projectile Impact and Torpedo Events

**What it does:** Adds combat log subscriptions for three events that currently fire on the
event bus but are not captured by `CombatLog`:

- `projectile_impact` — railgun round hits a ship; log the hit location, subsystem damaged,
  damage amount, and firing solution confidence at time of fire.
- `torpedo_detonation` — torpedo reaches warhead proximity; log detonation range, target,
  and damage cascade result.
- `torpedo_intercepted` — PDC kills an incoming torpedo; log the intercept range and which
  PDC mount engaged.

**Why it matters:** The design principle "player should understand WHY" depends entirely on
the combat log. If a railgun round hits the reactor and the freighter loses power, the player
needs to read that causal chain in the log — not infer it from health bars dropping.

**Key files affected:** `hybrid/systems/combat/combat_log.py` (add event handlers),
`hybrid/simulator.py` (verify event bus subscriptions are in place).

**Estimated complexity:** Small.

**Dependencies:** None.

---

### 1.6 `sim_time` Consistency Fix

**What it does:** Audits all uses of `getattr(ship, "sim_time", self.time)` in
`hybrid/simulator.py` and the combat system. Currently `sim_time` is looked up on the ship
object but is actually owned by the simulator, meaning the fallback `self.time` is always used.
The fix is to inject `sim_time` onto the ship at the start of each tick, or to pass it
explicitly to all systems that need it.

**Why it matters:** PDC cooldown timing and weapon heat calculations both use `sim_time`. If
the value is wrong, PDC can fire more rapidly than intended and weapon heat does not dissipate
correctly, which breaks the PDC balance fix in 1.2.

**Key files affected:** `hybrid/simulator.py` (`tick` method), `hybrid/systems/combat/combat_system.py`,
`hybrid/systems/weapons/truth_weapons.py`.

**Estimated complexity:** Small.

**Dependencies:** 1.1 (file split) recommended first.

---

### 1.7 GUI Ship ID Assignment Fix

**What it does:** Audits the client connection flow for the case where a client connects but
does not have a ship assignment. After PR #199 fixed missing ship assignment, verify that
all telemetry paths gracefully handle a `None` ship reference and return a clear error rather
than an unhandled exception that silently drops the connection.

**Why it matters:** Ship assignment is the most common point of failure for new players
starting the game. A silent disconnect with no error message is a poor first impression.

**Key files affected:** `gui/ws_bridge.py`, `server/station_server.py`,
`server/stations/station_manager.py`.

**Estimated complexity:** Small.

**Dependencies:** None.

---

### 1.8 Formation Autopilot Fix

**What it does:** Investigates and fixes the case where fleet formation autopilot produces
oscillation or overshoot when a formation member tries to hold position relative to a
maneuvering flagship. The rendezvous autopilot approach-phase fix (PR #198) addressed
the intercept case; the formation case needs the same treatment.

**Why it matters:** Oscillating wingmen look wrong and make the fleet unusable for escort
missions. The formation system exists but is only useful if ships can actually hold position.

**Key files affected:** `hybrid/fleet/formation.py`, `hybrid/navigation/autopilot/` (whichever
program handles formation-hold), `hybrid/fleet/ai_controller.py`.

**Estimated complexity:** Medium.

**Dependencies:** None.

---

### 1.9 Test Coverage for Nine Untested Systems

**What it does:** Adds at least one meaningful test per system that currently has no test file.
Based on the system registry, the following have no test coverage:

- `BioMonitorSystem`
- `OpsSystem`
- `CommsSystem`
- `ScienceSystem`
- `FleetCoordSystem`
- `EngineeringSystem`
- `CrewFatigueSystem` (impairment wiring, not just data model)
- `ECMSystem` (jammer effectiveness calculation)
- `DockingSystem`

Tests should cover: system initializes from config, tick does not raise, one representative
command returns success.

**Why it matters:** Systems without tests are invisible to regressions. Every time a new
feature touches `hybrid/ship.py` or the event bus, any of these systems could silently break.

**Key files affected:** `tests/systems/` (new files), one test file per system.

**Estimated complexity:** Medium in aggregate (small per system). The pattern is repetitive.

**Dependencies:** 1.1 (file split) so test imports are stable.

---

### 1.10 Reactor Heat Telemetry Exposed to GUI

**What it does:** Confirms that the heat schema in `hybrid/systems_schema.py` includes
current temperature, dissipation rate, and overheat threshold, and that these fields reach
the engineering station telemetry. The thermal system was added in the overhaul but its
telemetry exposure to the GUI has not been verified.

**Why it matters:** The engineering station's heat management panel cannot display anything
if the telemetry path is broken. Players need to see reactor temperature to make meaningful
decisions about radiator deployment and cold-drift.

**Key files affected:** `hybrid/systems_schema.py`, `server/stations/station_telemetry.py`,
`hybrid/telemetry.py`, `gui/components/engineering-control-panel.js`.

**Estimated complexity:** Small (mostly verification and a small telemetry registration if missing).

**Dependencies:** None.

---

## Tier 2: Gameplay Depth (2–4 weeks)

With the foundations hardened, the next priority is making the game worth playing for more
than one scenario. These features give the player more situations to think through and more
tools to think with.

---

### 2.1 Three New Scenarios

**What it does:** Designs and implements three new YAML scenarios using the existing scenario
loader format.

**Scenario A — Fleet Escort (Convoy Defense):** Player commands a corvette escorting a freighter
through a transit corridor. Two enemy frigates execute a pincer intercept. Win condition:
freighter reaches the transit endpoint with propulsion intact. Lose conditions: freighter
propulsion destroyed, or player ship destroyed. Forces the player to choose between staying
close to the freighter (PDC coverage) and maneuvering to engage the frigates (railgun range).

**Scenario B — Station Defense:** Player is stationed near a fixed orbital installation. An
enemy destroyer performs a high-speed attack run with torpedoes. Win: destroy or drive off
the destroyer before it fires a third torpedo salvo. Lose: station destroyed. Introduces
the concept that the player is not always the maneuvering party — sometimes you defend a
fixed point.

**Scenario C — Convoy Ambush (Attacker):** Role reversal from Scenario A. Player commands
a frigate interdicting a freighter running under ECM cover. The freighter's identity is
initially unknown (unknown contact classification). Player must approach to get a science
scan, confirm hostile classification, then achieve mission kill on the drive without
destroying the hull (cargo seizure, not destruction). Win: freighter drive destroyed, hull
intact. Lose: freighter escapes at 200 km range, or player fires on a neutral contact.

**Why it matters:** The tutorial intercept scenario teaches the basics. These three scenarios
teach fleet geometry, point defense decision-making, contact classification under uncertainty,
and asymmetric engagement roles. Each scenario exercises a different combination of the new
systems from the overhaul.

**Key files affected:** `scenarios/` (3 new YAML files), `hybrid/scenarios/objectives.py`
(may need new objective types for "station health above threshold" and "hull intact"),
`hybrid/fleet/ai_controller.py` (new AI behavior: pincer intercept, attack run pattern).

**Estimated complexity:** Large overall (medium per scenario, plus AI behavior work).

**Dependencies:** 1.8 (formation autopilot fix) for Scenario A. 1.5 (combat log events)
so players can read what happened in all three.

---

### 2.2 AI Doctrine System

**What it does:** Extends `hybrid/fleet/ai_controller.py` with doctrine-level behaviors:

- **Coordinated salvos:** When two AI ships have the same target locked, they time railgun
  fire so rounds arrive within a 2-second window, overwhelming PDC saturation.
- **Evasion doctrine:** AI ships under fire from railguns execute random attitude changes
  at intervals calculated from the railgun's time-of-flight to the current range, making
  their trajectory harder to predict.
- **Retreat conditions:** AI ships with propulsion below 50% health attempt to disengage
  and hold position rather than continuing a losing engagement.
- **Target prioritization:** AI selects targets based on threat assessment — ships with
  active railguns take priority over ships in PDC-only range.

**Why it matters:** The current AI only knows IDLE, PATROL, INTERCEPT, ESCORT, and ATTACK.
These are single-ship behaviors. The scenarios in 2.1 require multi-ship cooperation and
reactive evasion. Without doctrine, AI ships charge straight at the player and fire without
coordination, which teaches the player nothing about real engagement geometry.

**Key files affected:** `hybrid/fleet/ai_controller.py`, `hybrid/fleet/fleet_manager.py`
(for coordinated salvo timing), `hybrid/systems/sensors/passive.py` (AI needs to read
sensor state to make threat assessments).

**Estimated complexity:** Large.

**Dependencies:** 1.8 (formation autopilot), 2.1 (scenarios give AI a context to exercise
in), 1.9 (tests, so doctrine behaviors can be unit-tested).

---

### 2.3 Flight Computer Module: Clean High-Level Nav API

**What it does:** The `FlightComputer` system already exists in `hybrid/systems/flight_computer/`.
This item is about exposing a clean, documented API of four named programs that can be called
from the GUI without the player needing to understand autopilot internals:

- `navigate_to(position, speed_profile)` — compute and execute a least-time trajectory
  to a point, with configurable arrival speed.
- `intercept(contact_id, relative_velocity_at_intercept)` — compute intercept and match
  velocity for boarding/inspection range; distinguish from combat intercept (which arrives
  fast).
- `orbit(contact_id, radius_km, direction)` — maintain a circular orbit around a contact
  at specified radius, using continuous thrust corrections.
- `hold_station(position)` — null all velocity relative to a point and maintain it against
  perturbations.

Each program should log its current phase to the helm telemetry so the GUI can display
`Burning to intercept | 00:04:23 to TCA` rather than raw autopilot state strings.

**Why it matters:** The helm station currently exposes low-level autopilot programs. A
new player cannot distinguish "intercept for combat" from "intercept for docking." Wrapping
these in named, intent-clear commands reduces cognitive load and allows the tutorial to
say "use navigate_to to reach the station" without teaching autopilot internals first.

**Key files affected:** `hybrid/systems/flight_computer/system.py`, `hybrid/commands/navigation_commands.py`,
`server/stations/station_types.py` (HELM permissions), `gui/components/flight-computer-panel.js`,
`gui/components/helm-workflow-strip.js` (phase display).

**Estimated complexity:** Medium.

**Dependencies:** 1.3 (sim_time fix) so autopilot timing is accurate. 1.1 (file split)
so helm command routing is clean.

---

### 2.4 Damage Visualization in the GUI

**What it does:** When a subsystem takes damage, the corresponding GUI panel shows a visual
degradation state. Three levels:

- **Impaired (50% health):** Panel border turns amber; status text shows "IMPAIRED".
  Data continues to display but with a visual noise overlay (CSS filter or scanline effect).
- **Destroyed (0% health):** Panel goes dark; displays "OFFLINE — [system name] DESTROYED"
  with static texture. Data reads stop updating (last known value shown in grey).
- **Under attack (health dropping this tick):** Brief red flash on the panel border, same
  as a hull hit indicator.

This is a CSS and JavaScript change only — the server already publishes `ship_damaged` and
the subsystem health data is in telemetry. The GUI needs to read it and apply state classes.

**Why it matters:** Currently damage is invisible in the GUI unless you read the combat log.
A pilot under attack cannot afford to read logs — they need peripheral visual feedback.
This is the single highest-impact GUI change for combat legibility.

**Key files affected:** `gui/components/` (all station panels need to check subsystem health
from `stateManager`), `gui/styles/` (new CSS classes for impaired/destroyed states),
`gui/js/main.js` or a new `gui/js/damage-state-manager.js` module.

**Estimated complexity:** Medium (the pattern is repetitive across panels, but each needs
individual handling).

**Dependencies:** 1.5 (combat log events), so the damaged event triggers correctly.

---

### 2.5 Tutorial System: Guided First Mission

**What it does:** Adds a structured tutorial overlay to the existing tutorial intercept
scenario (`scenarios/01_tutorial_intercept.yaml`) that walks a new player through each
station and action in sequence:

1. Connect as HELM, observe contact
2. Navigate to sensor range of the freighter
3. Switch to TACTICAL, establish lock
4. Get a firing solution
5. Fire railgun, observe result
6. Read combat log entry

Each step has a check condition (`stateManager` getter or WebSocket poll) that auto-advances
when the player completes the action. Steps that the player cannot currently perform show a
greyed hint: "Approach to within 60,000 km to establish targeting lock."

The system already has scaffolding in `gui/components/tutorial-overlay.js`. This item
extends it to cover the full mission flow rather than just the first few connection steps.

**Why it matters:** Without guided first-play, a new crew member lands on the helm station
and has no idea what any of the panels mean. The flight computer, targeting pipeline, and
firing solution system are not self-explanatory. The tutorial is the difference between a
player who understands the game in 10 minutes and one who quits.

**Key files affected:** `gui/components/tutorial-overlay.js`, `scenarios/01_tutorial_intercept.yaml`
(add hint metadata), `gui/js/autopilot-utils.js` (tutorial polls these for state checks).

**Estimated complexity:** Medium.

**Dependencies:** 2.3 (flight computer API, so tutorial can reference clean command names),
2.4 (damage visualization, so the tutorial can show "your sensors took damage" visually).

---

### 2.6 Fuel Estimation Display

**What it does:** The `FlightComputer` system already computes delta-v budgets. This item
exposes two derived values in the helm telemetry:

- **Estimated burn time** for the current autopilot program, computed from current thrust
  and mass using the Tsiolkovsky equation.
- **Fuel remaining after maneuver** as a percentage, so the player can see "this intercept
  will leave you at 34% fuel."

Also fixes the fuel estimation for multi-phase autopilot programs (burn-coast-burn) where
the current display only shows the first burn phase.

**Why it matters:** "Mission kill the freighter's drive" loses meaning if the player runs
out of fuel after the first engagement and can't maneuver home. Fuel state is a hard physics
constraint that should be visible and predictable, not discovered after the fact.

**Key files affected:** `hybrid/systems/flight_computer/system.py`, `hybrid/telemetry.py`,
`gui/components/flight-data-panel.js`.

**Estimated complexity:** Small.

**Dependencies:** 2.3 (flight computer API).

---

## Tier 3: Advanced Systems (1–2 months)

These features expand the simulation's depth in ways that require either new hardware
abstractions or significant AI work. They are not needed for the game to be playable,
but they are needed for the game to be interesting at higher skill levels.

---

### 3.1 Drone System

**What it does:** Adds a new ship class `drone` with a stripped-down system set: propulsion,
RCS, sensors (passive only), and optionally a single PDC or railgun. Drones are launched
from a parent ship, have a finite delta-v budget, and operate under a simple AI doctrine
(patrol, attack, return). A drone bay module is added to destroyer and cruiser class configs.

The drone is a full `Ship` object in the simulator, not a projectile. It ticks like any other
ship and is destroyed by the same damage model.

**Why it matters:** Drones introduce a new category of tactical decision: deploy expendable
assets to extend sensor coverage, force enemy PDC to spend rounds on cheap targets, or hold
a chokepoint while the parent ship repositions. They also require the player to think about
mass and fuel budget when deciding how many to carry.

**Key files affected:** `ship_classes/drone.json` (new), `hybrid/systems/combat/combat_system.py`
(drone launch command), `hybrid/fleet/ai_controller.py` (drone AI doctrine),
`hybrid/simulator.py` (drone spawning from a parent ship event).

**Estimated complexity:** Large.

**Dependencies:** 2.2 (AI doctrine, since drones need their own doctrine parameters),
Tier 1 complete (so the ship system base is stable).

---

### 3.2 Multi-Weapon Gimbal Mounts

**What it does:** Extends the weapon mount model so that mounts with `gimbal: true` in their
JSON config rotate to track a target within their firing arc, rather than requiring the ship
to point at the target.

The rotation is simulated: the gimbal has a slew rate (degrees per second), so a fast-crossing
target can exit the firing arc before the gimbal catches up. The current heading of each
gimbal is tracked and exposed in telemetry.

Also adds per-barrel overheat tracking so a twin-railgun mount can fire barrel-alternating,
giving effectively half the cycle time but requiring both barrels to cool independently.

**Why it matters:** Currently all weapons on a ship require the ship itself to point at the
target. This makes beam-riding, crossing-track shots impossible and removes an entire category
of tactical geometry. Gimballed weapons let a corvette engage targets off the bow arc, which
is historically accurate for naval combat and adds significant maneuvering options.

**Key files affected:** `hybrid/systems/weapons/truth_weapons.py` (`WeaponMount` class),
`hybrid/systems/combat/combat_system.py` (gimbal tracking per tick),
`ship_classes/*.json` (add `gimbal` and `slew_rate_deg_per_s` to applicable mounts).

**Estimated complexity:** Large.

**Dependencies:** 1.1 (truth_weapons.py split), 1.2 (PDC balance, since gimballed PDC
changes the defense geometry significantly).

---

### 3.3 Science Station Completion

**What it does:** The `ScienceSystem` already implements contact mass estimation, drive type
inference, and threat assessment. This item wires those capabilities to the GUI science panel
and adds two missing commands:

- `science_spectral_analysis(contact_id)` — identifies propulsion type from IR emission
  spectrum (distinguishes Epstein from chemical from fusion). Returns drive type confidence
  and estimated ISP range.
- `science_composition_scan(contact_id)` — estimates hull composition from active radar
  return profile. Returns armor thickness estimate and probable ship class.

Both commands have range limits (effective only inside 20 km for composition scan,
50 km for spectral) and require the target to be actively tracked.

**Why it matters:** The science station currently has no player-facing gameplay hook. Science
analysis converts sensor returns into actionable intelligence: "that contact has an Epstein
drive rated for 2.5g sustained" tells the tactical officer that it's a warship, not a freighter.
This intelligence feeds directly into firing solution decisions and doctrine choices.

**Key files affected:** `hybrid/systems/science_system.py`, `hybrid/commands/` (new
science_commands.py), `server/stations/station_types.py` (SCIENCE station permissions),
`gui/components/` (science station panel).

**Estimated complexity:** Medium.

**Dependencies:** 1.9 (test coverage), 2.4 (damage visualization, since science panel
needs the same impaired/destroyed state handling).

---

### 3.4 Comms and IFF Completion

**What it does:** The `CommsSystem` is scaffolded. This item completes three features:

- **Hail and response:** A player can hail an unknown contact. If the contact is an AI ship
  with an IFF transponder, it responds with its class, name, and faction code. The response
  travels at speed of light (distance / c delay). If the contact has EMCON active, no response.
- **Faction diplomatic state:** A `DiplomaticState` enum (ALLIED, NEUTRAL, HOSTILE, UNKNOWN)
  that affects whether contacts respond to hails, what IFF codes they broadcast, and whether
  they are valid targets in objective evaluation.
- **Transponder spoofing:** A ship with `transponder_spoofable: true` can set a false IFF
  code. The science station's spectral scan can detect a mismatch between declared class
  and drive signature (e.g., a ship claiming to be a freighter but burning at 2.5g).

**Why it matters:** IFF is the foundation of Rules of Engagement. The scenario Convoy Ambush
(2.1.C) depends on this: the player must confirm hostile classification before firing,
and a mistaken fire-on-neutral ends the mission. Without IFF gameplay, classification is
binary and trivial.

**Key files affected:** `hybrid/systems/comms_system.py`, `hybrid/scenarios/objectives.py`
(add "do not fire on neutral" objective type), `server/stations/station_types.py` (COMMS
station permissions), `gui/components/` (comms panel with hail/response log).

**Estimated complexity:** Medium.

**Dependencies:** 3.3 (science station, for transponder mismatch detection).

---

### 3.5 Crew System Completion: Injury, Morale, Skill Progression

**What it does:** Three additions to the existing crew system:

- **Injury from combat damage:** When a compartment takes damage above a threshold, crew
  assigned to that station have a probability of injury (proportional to damage severity).
  Injured crew have reduced skill efficiency and cannot be reassigned until treated.
- **Morale system:** Crew morale tracks over the mission based on: casualties taken,
  own ship damage level, mission objective progress, and time under fire. Low morale
  increases fatigue accumulation rate.
- **Skill progression:** After a mission, crew members who used their skills under pressure
  (high-g, combat) gain experience points. At thresholds, their `SkillLevel` advances from
  NOVICE to MASTER. This state persists across missions in campaign mode (Tier 5).

**Why it matters:** The `CrewMember` dataclass and `SkillLevel` enum already exist in
`server/stations/crew_system.py`. The g-load impairment model in Tier 1 will connect
fatigue to performance. This tier closes the loop: crew are not just performance modifiers,
they are resources that degrade, recover, and improve. Losing a skilled gunner to a reactor
hit is a meaningful loss.

**Key files affected:** `server/stations/crew_system.py`, `hybrid/systems/crew_fatigue_system.py`,
`hybrid/ship.py` (compartment damage → injury event), `hybrid/core/event_bus.py` (new
`crew_injured` event type).

**Estimated complexity:** Large.

**Dependencies:** 1.4 (crew fatigue wired to combat), Tier 2 complete (scenarios give
crew mechanics a context to play in).

---

## Tier 4: Scale and Infrastructure (2–3 months)

These items address the engineering concerns that limit how large or how robust the simulator
can become. They are not player-facing features but they are prerequisites for Tier 5.

---

### 4.1 Fleet-Scale Combat Performance

**What it does:** Profiles and optimizes the simulator tick loop for 8+ ships in active
combat. Specific targets:

- Sensor interaction loop: currently O(n²) across all ships. Replace with spatial partitioning
  (simple grid or k-d tree) to reduce to O(n log n) for large fleets.
- Projectile manager: benchmark active projectile count vs. tick duration. Add a LOD system
  that skips detailed intercept checks for projectiles more than 500 km from any ship.
- Per-ship event bus: the current design gives each ship its own event bus, which creates
  significant overhead when 10 ships each fire events every tick. Evaluate a shared bus
  with ship-ID filtering.

**Why it matters:** The current tick rate is 10 Hz with tested capacity of 10 ships at ~15%
CPU. A 3-ship fleet engagement adds 3 AI ships plus projectiles; a 6v6 engagement would
likely push the tick over 100ms, breaking real-time. Fleet-scale scenarios (Tier 2.1) need
to remain playable.

**Key files affected:** `hybrid/simulator.py` (tick loop and sensor interaction), `hybrid/systems/combat/projectile_manager.py`,
`hybrid/core/event_bus.py`.

**Estimated complexity:** Large.

**Dependencies:** 2.1 (scenarios to benchmark against), 2.2 (AI doctrine to generate
realistic multi-ship load).

---

### 4.2 Replay System

**What it does:** Records the simulation state at each tick to a structured JSON log.
Adds a `replay_start` / `replay_stop` command pair. A separate replay viewer (either
a standalone HTML page or a server mode) can load the log and step through it with
a scrubber control.

The replay does not re-simulate — it replays recorded state snapshots. This means replay
is deterministic and does not require re-running AI or physics. The viewer shows the
tactical display with all ship positions, heading, and active weapons at each tick.

Recording already partially exists (the event log captures events). This item adds full
state snapshots at each tick and a viewer that can consume them.

**Why it matters:** After-action review is the primary learning tool for hard-skill combat
games. A player who loses the tutorial intercept wants to know why: was the firing solution
confidence too low? Did they approach on the wrong vector? Was the PDC still cooling when
the torpedo hit? Without replay, the answer is "read the combat log," which is adequate
for a single engagement but insufficient for multi-ship battles.

**Key files affected:** `hybrid/simulator.py` (state snapshot recorder), `server/station_server.py`
(replay commands), new `tools/replay_viewer.html` or `gui/replay.html`.

**Estimated complexity:** Large.

**Dependencies:** 4.1 (performance, since recording state at every tick adds memory pressure),
1.5 (combat log events, to include causal chain in the replay).

---

### 4.3 CI/CD Pipeline

**What it does:** Adds a GitHub Actions workflow that runs on every pull request to `main`:

1. `pytest tests/` — full test suite, fail on any failure.
2. `python server/main.py --dry-run` — server starts and exits cleanly.
3. `python -m py_compile hybrid/**/*.py` — syntax check all Python files.
4. Line-count check: fail if any `.py` file exceeds 400 lines (warn at 300).

The workflow runs in the `.venv` environment with pinned dependencies.

**Why it matters:** Every command registration requires three-place registration. The command
registration linter agent output (`.automaker/features/command-registration-linter/`) confirms
there is already tooling for this. Automated CI catches missed registrations, broken imports,
and oversized files before they reach main. Without CI, the cost of regression-finding shifts
to manual testing after the fact.

**Key files affected:** `.github/workflows/ci.yml` (new), `tools/` (any lint helpers).

**Estimated complexity:** Small.

**Dependencies:** 1.9 (test coverage, so the CI has meaningful tests to run).

---

### 4.4 Network Robustness

**What it does:** Four improvements to the WebSocket and TCP layers:

- **Reconnection handling:** If a client disconnects and reconnects within 30 seconds, it
  is reassigned to its previous station with state restored (ship assignment, station claim).
  Currently reconnection creates a fresh anonymous session.
- **Latency masking:** The GUI interpolates ship position between telemetry ticks (10 Hz server)
  so the tactical display does not stutter on a 50ms LAN connection.
- **Command acknowledgement:** Server returns a command ID with every response. Client can
  display a "pending" state until the ack arrives, preventing double-clicks from firing
  two railgun rounds.
- **Connection health indicator:** Status bar shows server tick rate and last telemetry age.
  If telemetry is more than 500ms stale, the indicator turns red.

**Why it matters:** Multi-crew sessions depend on reliable network behavior. A tactical officer
who disconnects mid-battle and cannot rejoin their station is a broken play session. Latency
masking is the difference between a 10 Hz tactical display that looks like a slideshow and
one that looks fluid.

**Key files affected:** `gui/ws_bridge.py`, `server/station_server.py`,
`gui/js/main.js` (interpolation), `gui/components/status-bar.js` (health indicator).

**Estimated complexity:** Large.

**Dependencies:** None, but benefits from 4.1 (stable tick performance to interpolate).

---

### 4.5 Modding Support: Scenario Editor and Custom Ship Classes

**What it does:** Two tooling additions:

- **Scenario editor:** A JSON/YAML form in the GUI (or a standalone web page) that lets
  Flax define ship starting positions, objectives, and AI doctrines without editing YAML
  directly. Outputs a valid scenario file that the existing loader can consume.
- **Custom ship class validation:** A command-line tool (`tools/validate_ship_class.py`)
  that takes a JSON ship class file and checks it against the schema: required fields,
  mass plausibility, system references exist, weapon mounts have valid firing arcs.

**Why it matters:** The current scenario format requires understanding the YAML structure
and the objective DSL. The ship class format requires knowing which system types are
registered. A validation tool catches the "silent failure at runtime" class of error
described in CLAUDE.md. A scenario editor lowers the barrier to creating new missions.

**Key files affected:** `hybrid/ship_class_registry.py` (add validation logic),
`tools/validate_ship_class.py` (new), `gui/` (scenario editor page, optional).

**Estimated complexity:** Medium.

**Dependencies:** 4.3 (CI, so the validator is also run in CI against existing ship class files).

---

## Tier 5: Multiplayer and Polish (3+ months)

These items represent the long-horizon vision for the project. They are architecturally
dependent on everything in Tiers 1–4 being stable.

---

### 5.1 Full Multiplayer: Multiple Human Crew per Ship

**What it does:** The station architecture already supports multiple simultaneous clients
claiming different stations on the same ship. This item completes the multi-crew experience:

- Station handoff protocol: the Captain station can force-transfer a station to another
  connected client.
- Crew awareness: each station panel shows which stations are currently claimed and by whom.
- Cross-station communication: an in-game text channel between crew on the same ship,
  separate from the hail/radio comms used for ship-to-ship communication.
- Permission escalation: a Crew-rank player can request Officer-rank access; the Captain
  client sees the request and approves or denies.

**Why it matters:** The simulation was designed for multi-crew play from the architecture up.
Realizing that design completes the core loop: a pilot, a gunner, and an engineer each
have roles that require coordination under pressure. A solo player can handle all stations
but at degraded efficiency; a full crew of four is genuinely more effective.

**Key files affected:** `server/stations/station_manager.py`, `server/station_server.py`,
`gui/components/bridge-controls-bar.js`, `gui/components/` (crew awareness panel).

**Estimated complexity:** Large.

**Dependencies:** 4.4 (network robustness, essential for multi-human sessions), Tier 4 complete.

---

### 5.2 Campaign Mode

**What it does:** Connects scenarios into a sequence where ship damage and crew state persist
between missions. After a mission:

- Unrepaired damage carries forward to the next scenario's starting state.
- Crew skill progression from 3.5 accumulates across the campaign.
- Available scenarios may unlock based on previous outcomes (destroyed the freighter's
  reactor instead of the drive → different next scenario).

Campaign state is saved to a JSON file. The server can load a campaign save at startup
with `--campaign campaign_save.json`.

**Why it matters:** Individual scenarios teach individual skills. A campaign teaches resource
management: do you push through with a damaged sensor array, or take the repair time and
face a harder next scenario? This is the hard sci-fi equivalent of strategic-layer decisions.

**Key files affected:** `hybrid/scenarios/` (new `campaign.py`), `server/main.py`
(campaign load/save), `scenarios/` (campaign definition YAML linking existing scenarios).

**Estimated complexity:** Large.

**Dependencies:** 3.5 (crew progression), 2.1 (multiple scenarios to chain), 4.4 (network
stability so a campaign session can be interrupted and resumed).

---

### 5.3 Sound Design

**What it does:** Adds Web Audio API sound effects to the GUI. Triggered by event bus
events arriving via WebSocket:

- `weapon_fired` → railgun charge and fire crack, PDC burst fire
- `projectile_impact` → hull hit thud
- `torpedo_detonation` → detonation thump
- `ship_damaged` → system failure tone
- `autopilot_phase_change` → navigation chime
- Ambient: low-frequency reactor hum that varies with reactor load; propulsion burn tone
  that scales with throttle.

All sounds are optional and respect a volume control. No external audio library required —
Web Audio API is built into all modern browsers.

**Why it matters:** Sound completes the information channel. A player monitoring five panels
cannot watch all of them simultaneously. An auditory alert for incoming torpedo lock frees
their eyes for tactical decisions. The ambient reactor hum communicates power state without
requiring the engineering panel to be visible.

**Key files affected:** `gui/js/` (new `audio-manager.js`), `gui/index.html` (load audio module),
`gui/js/main.js` (connect event stream to audio manager), `gui/assets/sounds/` (audio files).

**Estimated complexity:** Medium.

**Dependencies:** 1.5 (combat log events so audio has accurate triggers), 4.4 (network robustness
so audio events are not delayed).

---

### 5.4 Accessibility

**What it does:** Four accessibility additions:

- **Colorblind modes:** Three alternative color schemes (deuteranopia, protanopia, tritanopia)
  for the tactical display contact icons and subsystem status indicators. Selectable from
  the bridge controls bar.
- **Keyboard remapping:** All keyboard shortcuts (1–6 for views, station-specific keys)
  configurable via a settings panel that writes to `localStorage`.
- **Screen reader labels:** All interactive elements get `aria-label` attributes. The
  tactical display publishes a text summary of contacts (`aria-live` region).
- **High contrast mode:** CSS class override that increases text contrast and removes
  decorative overlays (scanlines, glow effects) for players who find them distracting.

**Why it matters:** The GUI was built with decorative styling (scanlines, glow effects, tier
color identity). These are valuable for immersion but can be barriers for players with visual
impairments. A game about reasoning through physics should be accessible to anyone who can
reason through physics.

**Key files affected:** `gui/styles/tiers.css`, `gui/styles/` (new `accessibility.css`),
`gui/components/bridge-controls-bar.js` (accessibility settings UI),
`gui/index.html` (ARIA landmark structure).

**Estimated complexity:** Medium.

**Dependencies:** None. Can be worked in parallel with any Tier 5 feature.

---

### 5.5 Leaderboards and Mission Scoring

**What it does:** Adds a mission scoring system:

- **Score formula:** Time to mission kill, ammunition expended, own ship damage taken,
  and crew casualties combine into a final score. Each scenario has a par time and a
  par ammunition budget.
- **Local leaderboard:** Top 10 scores per scenario saved to a local JSON file.
- **After-action report:** A post-mission screen showing the score breakdown, a comparison
  to par, and three specific "you could improve by..." observations derived from the
  combat log (e.g., "3 railgun rounds missed due to firing solution confidence below 60%").

**Why it matters:** The after-action report is the most direct implementation of "player
should understand WHY." It does not just score the player — it explains what happened and
what they could do differently. This transforms loss from frustrating to instructive.

**Key files affected:** `hybrid/scenarios/mission.py` (scoring logic), new
`hybrid/scenarios/scoring.py`, `gui/` (after-action report screen), `server/station_server.py`
(score reporting command).

**Estimated complexity:** Medium.

**Dependencies:** 1.5 (combat log events, for the after-action analysis), 2.1 (scenarios,
to score), 4.2 (replay, so the after-action report can link to a replay).

---

## Cross-Cutting Concerns

These are not features but constraints that apply across all tiers.

### Command Registration Discipline

Every feature that adds a new server command must register it in all three places:
`hybrid/command_handler.py`, the relevant `hybrid/commands/*.py` spec file, and
`server/stations/station_types.py`. This is the most common source of silent failures in
the codebase. The command registration linter (`.automaker/features/command-registration-linter/`)
should be run after every command addition.

### File Size Budget

No Python file should exceed 300 lines. The Tier 1 refactoring establishes this baseline.
When adding features in Tier 2+, split new code into separate files rather than appending
to existing ones. The test for whether a file is too large: "can I describe what this file
does in one sentence?" If not, it needs splitting.

### Documentation Sync

KNOWN_ISSUES.md and FEATURE_STATUS.md are both out of date as of the overhaul branch.
Both should be updated immediately after the branch merges, before any Tier 2 work begins.
Stale documentation is worse than no documentation because it causes agents and developers
to build on wrong assumptions.

### Test-First for Combat Systems

Any change to truth weapon specs, damage model values, or autopilot parameters must be
accompanied by a test that encodes the intended behavior. These are the systems where
a well-intentioned balance tweak can silently break the intercept scenario. A test that
asserts "PDC at 1,000m hits torpedoes at >60% probability" makes the balance expectation
explicit and detectable.

---

## Priority Summary Table

| Item | Tier | Complexity | Depends On |
|------|------|------------|------------|
| File size refactoring | 1 | Large | — |
| PDC balance fixes | 1 | Small | 1.1 |
| ECM distance falloff | 1 | Small | — |
| Crew fatigue wired to combat | 1 | Medium | — |
| Combat log events | 1 | Small | — |
| sim_time consistency | 1 | Small | 1.1 |
| GUI ship ID fix | 1 | Small | — |
| Formation autopilot fix | 1 | Medium | — |
| Test coverage (9 systems) | 1 | Medium | 1.1 |
| Reactor heat telemetry | 1 | Small | — |
| Three new scenarios | 2 | Large | 1.5, 1.8 |
| AI doctrine system | 2 | Large | 1.8, 2.1 |
| Flight computer API | 2 | Medium | 1.6, 1.1 |
| Damage visualization | 2 | Medium | 1.5 |
| Tutorial system | 2 | Medium | 2.3, 2.4 |
| Fuel estimation display | 2 | Small | 2.3 |
| Drone system | 3 | Large | 2.2, Tier 1 |
| Multi-weapon gimbals | 3 | Large | 1.1, 1.2 |
| Science station completion | 3 | Medium | 1.9, 2.4 |
| Comms and IFF completion | 3 | Medium | 3.3 |
| Crew injury and morale | 3 | Large | 1.4, Tier 2 |
| Fleet-scale performance | 4 | Large | 2.1, 2.2 |
| Replay system | 4 | Large | 4.1, 1.5 |
| CI/CD pipeline | 4 | Small | 1.9 |
| Network robustness | 4 | Large | — |
| Modding support | 4 | Medium | 4.3 |
| Full multiplayer | 5 | Large | 4.4, Tier 4 |
| Campaign mode | 5 | Large | 3.5, 2.1, 4.4 |
| Sound design | 5 | Medium | 1.5, 4.4 |
| Accessibility | 5 | Medium | — |
| Leaderboards and scoring | 5 | Medium | 1.5, 2.1, 4.2 |

---

*This plan documents what to build next, not what has been promised. Priorities will shift
as gameplay testing reveals what matters most to players. The hard sci-fi design principles
in CLAUDE.md are the arbiter: if a feature makes the player reason about physics, it belongs.
If it abstracts physics away, it does not.*
