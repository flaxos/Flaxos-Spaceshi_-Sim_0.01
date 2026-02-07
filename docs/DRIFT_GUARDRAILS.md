# Drift Guardrails (Hard Rules)

## What this repo is
- A real-time, physics-first tactical simulator with RCS attitude control and Epstein main-drive thrust.
- The **mission execution layer** for encounters, with outcomes delivered via `ResultSpec.json`.
- A sandbox for scenarios, training missions, and multi-station gameplay.

## What this repo is NOT
- The strategic campaign layer for Gate Horizons.
- A lore, economy, faction, or diplomacy engine.
- A narrative arbiter that bends physics to fit story beats.

## Hard sci-fi constraints
- Preserve hard-sci-fi assumptions unless canon explicitly changes them.
- No shields, inertial dampers, or hand-waved armour unless already in canon.
- No “magical tech” additions to justify gameplay without an explicit, documented basis.

## Drift types (watch list)
- **Magic tech creep:** adding non-canonical capabilities to make missions easier or more cinematic.
- **Interface creep:** expanding integration beyond `EncounterSpec.json`/`ResultSpec.json`.
- **LLM creep:** accepting model-invented lore, tech, or rules not grounded in the canon pack.

## Controls
- Treat Gate Horizons `canon/CANON.md` and `canon/STYLE_BIBLE.md` as the constraints for lore and aesthetics.
- Keep integration contract-only: no hidden state, no side channels, no shared runtime hooks.
- Document any new assumption explicitly and keep it scoped to the tactical layer.

## Contract-only boundary
- **Input:** `EncounterSpec.json`
- **Output:** `ResultSpec.json`
- No hidden coupling to Gate Horizons internal state or data models.

## AI agent constraints
- Any AI agent work must preserve the real-time RCS + Epstein model.
- Do not change the physics model to satisfy narrative or balance requests.
- Any assumptions or additions must be declared explicitly in documentation.

## Non-goals to avoid drift
- Do not implement campaign time progression, trade, or faction reputation.
- Do not introduce strategic planning logic.
- Do not embed Gate Horizons world state inside this repo.
