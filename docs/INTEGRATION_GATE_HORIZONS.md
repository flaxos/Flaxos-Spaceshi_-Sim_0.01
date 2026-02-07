# Gate Horizons Integration (Encounter Runner Mode)

## Purpose
This document defines the **contract-only integration boundary** between Flaxos Spaceship Sim and the Gate Horizons meta game. Flaxos is the real-time, physics-first tactical runtime. Gate Horizons is the strategic layer that operates at months-scale travel and campaign planning. The interface between them is limited to JSON artefacts so each system can evolve without tight coupling.

## Operating modes
**Standalone sandbox/scenarios**
- Local skirmishes, training missions, and multi-station play.
- No upstream dependency on Gate Horizons; this sim is fully runnable on its own.

**Linked encounter runner (future)**
- Gate Horizons supplies the encounter definition and consumes the outcome report.
- Flaxos executes the encounter at real-time cadence and reports results via the contract.

## Timescale separation
- **Real-time tactical:** Flaxos simulates RCS attitude control and Epstein thrust per tick.
- **Months-scale strategic:** Gate Horizons handles gate travel, campaign planning, and encounter generation.

## Encounter Runner Mode (conceptual)
In Encounter Runner mode, Flaxos accepts a complete, immutable encounter description and executes it as a real-time tactical mission using the existing RCS + Epstein drive model. Flaxos does not resolve campaign state, faction lore, or economy. It simply simulates the encounter, records outcomes, and returns a result report.

## Contract: `EncounterSpec.json` (input)
At minimum, the encounter specification must include:
- **Encounter metadata**: scenario name, version, seed, and time budget or termination conditions.
- **Actors**: ships and entities to spawn, with identifiers, factions (if relevant), and initial state (position, velocity, orientation, system loadouts, and any enabled/disabled systems).
- **Objectives**: mission goals, win/loss conditions, and scoring criteria.
- **Rules**: engagement constraints, sensor rules, legal actions, and any encounter-specific toggles.
- **Environment**: local space parameters that affect the encounter (e.g. reference frame, local hazards, visibility constraints), if required.

Flaxos treats this input as authoritative. If the information is not present in the contract, it is out of scope for this runtime.

## Contract: `ResultSpec.json` (output)
At minimum, the result report must include:
- **Outcome summary**: win/loss/neutral, objective completion, and score (if defined).
- **Losses and damage**: destroyed or disabled actors, and critical system states at mission end.
- **Resource usage**: fuel, munitions, power constraints, and other consumables.
- **Timeline/flags**: key events, mission flags, and termination reason.
- **Survivor state**: final ship states required for campaign continuity (position, velocity, hull status, and critical system status).

This report is a mission-level summary, not a full sim replay. Gate Horizons can decide how much detail it needs as long as the minimum contract remains stable.

## Non-goals (to prevent drift)
- No direct access to Gate Horizons world state, economy, or faction logic.
- No narrative arbitration beyond the contract’s objectives and rules.
- No changes to physics or system behaviour to satisfy lore or story beats.
- No hidden or implicit integration: all integration must go through `EncounterSpec.json` and `ResultSpec.json`.

## Notes on timescale
Gate Horizons operates across months of travel and planning. Flaxos executes the tactical engagement at real-time cadence. Keep the boundary sharp so strategic decisions stay in the meta layer, and tactical execution remains deterministic and physics-first here.
