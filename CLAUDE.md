# CLAUDE.md — Flaxos Spaceship Sim

## Project Overview
A Python-based spaceship combat simulation with client-server architecture. Hard sci-fi, physics-grounded combat with systemic weapon mechanics. The player reasons about combat through targeting pipelines, firing solutions, and subsystem damage — not click-and-pray.

**Repo:** `flaxos/Flaxos-Spaceshi_-Sim_0.01`
**Stack:** Python server + Web GUI (HTML/JS)
**Entry points:** `server/main.py` (server), `tools/start_gui_stack.py` (GUI launcher)

## Architecture
```
server/
  main.py              # Server entry point
  [game logic modules]
tools/
  start_gui_stack.py   # GUI launcher
gui/
  [web-based client]
```

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
| PDC (Narwhal-III) | 0-5km effective | 3 km/s | Auto-turret, ablative damage, point defense |

### Targeting Pipeline
`contact → track → lock → firing solution → fire`
- Track quality degrades with range and target acceleration
- Firing solutions have confidence scores
- Sensor damage degrades everything

### Subsystem Damage
- Levels: nominal (100%) → impaired (50%) → destroyed (0%)
- Systems: drive, RCS, sensors, weapons, reactor
- Cascading effects: sensors down = blind, drive down = sitting duck, RCS down = can't aim

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
