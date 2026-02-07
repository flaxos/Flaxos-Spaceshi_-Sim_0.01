# AI Agent Rules (Documentation + Guardrails)

## Scope and authorisation
- **Documentation-only unless explicitly authorised.**
- If a request is ambiguous, default to documentation updates and ask for clarity in a future turn.

## Preserve the physics model
- Never change the real-time RCS + Epstein drive model to fit narrative goals.
- Do not introduce incompatible assumptions (e.g., instant thrust, reactionless drives, or non-canonical tech).
- Hard-sci aesthetic constraints must remain compatible with the Gate Horizons canon pack.

## Contract-only boundary
- The integration boundary is **contract-only** via `EncounterSpec.json` and `ResultSpec.json`.
- No direct coupling to Gate Horizons internal state, economy, factions, or lore systems.
- Do not introduce ad-hoc hooks, shared state, or side-channel data exchange.

## Canon and storyboard sources
- For any lore, storyboard, or style work, treat the Gate Horizons canon pack as the source of truth.
- Cite `canon/CANON.md`, `canon/STYLE_BIBLE.md`, and `canon/STORYBOARD.md` when documenting narrative or visual constraints.

## Assumptions must be declared
- Declare any assumptions in documentation.
- If a new behaviour is proposed, document it as a **future consideration**, not a promise.

## Allowed AI usage
- Documentation drafting and editing.
- Scenario writing and encounter briefs (as content only).
- Test encounter drafting for QA or planning purposes.

## Disallowed AI usage
- Implementing physics changes to satisfy story outcomes.
- Injecting hidden behaviour or non-contract data exchange.
- Expanding scope into strategic or economic simulation.
