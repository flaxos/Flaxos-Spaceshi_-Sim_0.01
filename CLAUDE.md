# CLAUDE.md — Flaxos Spaceship Sim

## Project Overview
A Python-based spaceship combat simulation with client-server architecture. Hard sci-fi, physics-grounded combat with systemic weapon mechanics. The player reasons about combat through targeting pipelines, firing solutions, and subsystem damage — not click-and-pray.

**Repo:** `flaxos/Flaxos-Spaceshi_-Sim_0.01`
**Stack:** Python server + Web GUI (HTML/JS)
**Entry points:** `server/main.py` (server), `tools/start_gui_stack.py` (GUI launcher)

## Architecture
```
server/
  main.py              # ONLY server entry point — all server code lives here
tools/
  start_gui_stack.py   # GUI launcher
gui/
  [web-based client]
```

**Note:** `server/station_server.py` is DELETED. All server code lives in `server/main.py` (`UnifiedServer`). Any references to `station_server.py` in older docs are stale.

## Design Principles
- **Systemic, not scripted:** Weapons follow physics rules, outcomes emerge from those rules.
- **Hard sci-fi:** No magic. Railguns are dumb slugs. PDCs are short-range suppression. Range matters.
- **Mission kill > explosion:** Combat ends when subsystems are destroyed, not HP bars depleted.
- **Player should understand WHY:** Every miss, every hit should have clear feedback about what happened and why.

## Combat System (Current Design)

### Weapons
| Weapon | Range | Speed | Role |
|--------|-------|-------|------|
| Railgun (UNE-440) | 0-500km effective | 20 km/s | High-skill penetrator, 1 subsystem per hit |
| PDC (Narwhal-III) | 0-2km effective | 2 km/s | CIWS point defense, 3000 RPM, ablative damage at knife-fight range |
| Torpedo | 0-120s burn | ~4.6 km/s delta-v | Heavy guided munition, 50kg fragmentation warhead, anti-ship |
| Missile | 0-80km effective | ~6.7 km/s delta-v | High-G interceptor, 4 flight profiles, anti-ship |

### Missile Flight Profiles
Missiles support four midcourse guidance profiles:
- `direct` — straight intercept course (shared with torpedoes)
- `evasive` — randomized weave to complicate PDC intercepts
- `terminal_pop` — low approach then nose-up terminal dive
- `bracket` — splits trajectory to present multiple threat vectors

### Torpedoes vs Missiles
Torpedoes (250 kg, 32 m/s²) are slow heavy ordnance with a 50 kg fragmentation warhead and 100m blast radius — suited for large, slow targets. Missiles (95 kg, 105 m/s²) are light, fast, high-G with a 10 kg shaped charge and 30m blast radius — suited for maneuvering ships. Both fire from the same launcher hardpoints. The GUI weapon-controls panel has a TORPEDO/MISSILE toggle.

### Targeting Pipeline
`contact → track → lock → firing solution → fire`
- Track quality degrades with range and target acceleration
- Firing solutions have confidence scores
- Sensor damage degrades everything

### Subsystem Damage
- Levels: nominal (100%) → impaired (50%) → destroyed (0%)
- Systems: drive, RCS, sensors, weapons, reactor, radiators
- Cascading effects: reactor destroyed = propulsion/weapons/sensors all degraded to 0
- Armor model: per-section ablation (fore/aft/port/starboard/dorsal/ventral); ricochet above 70 degrees; PDC strips armor slowly, railguns punch through or ricochet

### Mission Progression
- Scenarios link via `next_scenario` field in YAML
- On mission complete, the GUI overlay shows a NEXT MISSION button if `next_scenario` is defined
- State machine: lobby → playing → ended

### Intercept Scenario
- Player corvette vs fleeing freighter
- Win: destroy target's drive (mission kill)
- Lose: own drive destroyed, target escapes, or ammo depleted

## Code Standards
- Python 3.10+
- Type hints on all function signatures
- Docstrings on classes and public methods
- Modules should be independent and testable
- No monolithic files — if a file exceeds ~300 lines, it needs refactoring
- All game state changes go through the server (client is display only)

## Command Registration Checklist
Adding a new server command requires registration in **three** places. Missing any one will cause the command to silently fail at runtime.

1. **Hybrid command handler** — `hybrid/command_handler.py` `system_commands` dict (maps command name → system + action)
2. **Command spec** — `hybrid/commands/navigation_commands.py` (or the relevant domain's command file) to define args and handler
3. **Station permissions** — `server/stations/station_types.py` `STATION_DEFINITIONS` → add the command to the correct station's `commands` set (HELM, TACTICAL, OPS, etc.)

If step 3 is missed, the command routes correctly through the hybrid layer but the station dispatcher rejects it as "Unknown command" because no station claims ownership. **Always grep `station_types.py` for the new command name before considering registration complete.**

## Autopilot / Physics Rules
- **Diagnose before fixing.** Trace data flow end-to-end and identify the root cause before writing code. Don't tweak thresholds — find the broken assumption.
- **Phase-aware acceleration.** Any braking/ETA calculation must specify WHICH phase's accel it needs. Never call `_get_effective_accel()` without considering whether measurements came from the current phase or a stale previous one. BURN accel ≠ BRAKE accel ≠ COAST accel.
- **Headless gate before autopilot PRs.** Before creating any autopilot PR, run `python3 tools/test_rendezvous.py --max-ticks 15000` and verify convergence to docking range (<50m, <1 m/s).
- **Sensor noise scales.** Position noise: up to 1km (distance-appropriate). Velocity noise: 2% of speed + 2 m/s floor. Never reuse `add_detection_noise()` for velocity — use `add_velocity_noise()`.

## Git / PR Workflow
- **One branch = one PR. Period.** Never push commits to a branch after its PR merges.
- New work after a PR merges: `git fetch origin && git checkout -b new-name origin/main`
- Before PR: `git log --oneline origin/main..HEAD` — verify exact commits. 0 commits = STOP.
- Before PR: `gh pr view <N> --json state` — if MERGED, create a new branch.
- Before PR: `git diff origin/main..HEAD --stat` — verify file changes match intent.

## When Working on This Project
1. **Read the codebase first** — run `find . -name "*.py" | head -30` and review structure
2. **Don't break the server** — always verify `python server/main.py` starts cleanly
3. **Test after changes** — run `python3 -m pytest tests/ -x -q` and verify all pass
4. **Commit small** — one logical change per commit
5. **Document decisions** — add comments explaining WHY, not just WHAT
6. **Diagnose first, fix second** — for physics/autopilot bugs, trace the data pipeline before writing code
7. **`server/station_server.py` is DELETED** — all server code lives in `server/main.py`. Never edit or reference `station_server.py`.
8. **Use `ship._all_ships_ref` for target resolution**, not `params.get('all_ships')` — the ship object carries a live reference to the current sim's ship dict, set each tick by `hybrid_runner.py`.
