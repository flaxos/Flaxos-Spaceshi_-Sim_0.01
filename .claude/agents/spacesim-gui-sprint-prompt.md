# Agent Teams Prompt: GUI Overhaul & Flight Computer Layer

## THE PROBLEM

The web GUI has never felt solid. The game has good underlying physics and
combat mechanics, but the player experience is disconnected from them.
There's no clean interface between "I want to fly over there and complete
a mission" and the raw thrust/RCS/physics layer underneath.

## WHAT WE WANT

A proper ship GUI where:
- Player can fly the ship, navigate, and complete basic missions through GUI controls
- A "flight computer" abstraction sits between player intent and physics
- Player gives high-level commands ("intercept that contact", "orbit this point",
  "match velocity with target") and the ship's computer computes the burns
- Granular manual control is STILL available — player can always override and
  fly stick-and-rudder if they want
- The GUI surfaces the right information at the right time (contacts, ship status,
  weapons, navigation) without overwhelming the player
- It follows web UI best practices — responsive, clean, keyboard accessible

## THE FLIGHT COMPUTER CONCEPT

Think of it like a real naval CIC (Combat Information Center) or aircraft autopilot:

```
PLAYER INTENT          FLIGHT COMPUTER         PHYSICS ENGINE
─────────────          ───────────────         ──────────────
"Intercept target" →   Calculates burn plan →  Executes thrust commands
"Hold position"    →   Station-keeping burns → Micro-corrections
"Evasive maneuver" →   Random jink pattern  →  RCS + main drive
"Manual control"   →   Pass-through mode    →  Direct stick input

The flight computer is a MODULE in the game logic, not just UI sugar.
It computes solutions and issues commands to the physics engine.
The GUI just talks to the flight computer.
```

## HOW TO USE THIS PROMPT

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
cd ~/Flaxos-Spaceshi_-Sim_0.01
claude
```

Then paste everything between the === lines below.

===

Read the entire codebase. Focus especially on:
- The GUI layer (gui/ directory, any HTML/JS/CSS)
- The server-client communication (how does the GUI talk to the server?)
- The physics/movement system (how ships move, thrust, rotate)
- The combat system (targeting, weapons)
- Any existing input handling or command processing

Then create an agent team with THREE teammates:

TEAMMATE 1 — "Flight Computer Engineer":
Scope: Build the flight computer module as a SERVER-SIDE Python module.

This is the critical missing layer between player intent and physics.
The flight computer should:

1. Accept HIGH-LEVEL commands:
   - navigate_to(position) — compute and execute burns to reach a point
   - intercept(target_id) — compute intercept course to a contact
   - match_velocity(target_id) — burn to match another ship's velocity
   - hold_position() — station-keeping with micro-corrections
   - orbit(position, radius) — maintain circular orbit around a point
   - evasive() — random jink pattern using RCS + main drive
   - manual_override() — pass raw stick input directly to thrusters

2. For each command, compute a BURN PLAN:
   - Which thrusters fire, for how long, at what throttle
   - Estimated time to completion
   - Fuel/propellant cost estimate
   - Confidence level (can we actually achieve this?)

3. Execute the burn plan by issuing commands to the physics engine
   each tick, adjusting for drift and error

4. Report status back: "executing", "on course", "correcting",
   "complete", "cannot comply" (not enough fuel, target out of range, etc.)

5. Be a clean Python module with clear interfaces:
   - Input: command + ship state + world state
   - Output: thruster commands + status
   - No GUI code. No network code. Pure game logic.

Implementation notes:
- Start with navigate_to and intercept as the first two commands
- Use proportional navigation or similar for intercept calculations
- The manual_override mode should be trivial — just pass through
- Add type hints and docstrings to everything
- Write it so it's testable without running the full game

TEAMMATE 2 — "GUI Architect":
Scope: Redesign and rebuild the web GUI.

Current state: assess what exists, identify what's broken or missing,
then rebuild with best practices.

The GUI should have these panels/views:

1. HELM (primary view):
   - Central: space view / tactical display showing contacts, course, vectors
   - Ship status bar: hull, subsystems, fuel, ammo (always visible)
   - Navigation controls: click-to-navigate on tactical display,
     or input coordinates, select from contacts list
   - Flight mode indicator: AUTO (flight computer) / MANUAL (direct control)
   - Throttle/heading controls for manual mode
   - Current flight computer command + status + ETA

2. TACTICAL (combat view):
   - Contact list with bearing, range, range-rate, threat level
   - Target selection and lock status
   - Weapons panel: select weapon, see ammo, fire
   - Targeting pipeline status: contact → track → lock → solution
   - Firing solution confidence indicator

3. SHIP STATUS (engineering view):
   - All subsystems with damage level (nominal/impaired/destroyed)
   - Fuel and ammo reserves
   - Velocity, acceleration, heading readouts

4. MISSION (objectives):
   - Current mission briefing
   - Objectives with completion status
   - Mission timer if applicable

Design principles:
- Dark theme (space game, obviously)
- Information hierarchy: most critical info is most prominent
- Don't show everything at once — use tabs or toggleable panels
- Keyboard shortcuts for common actions (T for target, F for fire, M for manual)
- WebSocket for real-time updates from server (or whatever the existing
  server-client protocol is — CHECK FIRST, don't assume)
- Mobile-responsive if possible (Flax sometimes runs this on Android)
- No framework bloat — vanilla HTML/CSS/JS or lightweight lib only
  (match whatever the project already uses)

CRITICAL: Check how the existing GUI communicates with the server BEFORE
redesigning. Don't break the protocol — extend it.

TEAMMATE 3 — "Integration & QA":
Scope: Wire everything together, test it, document it.

1. INTEGRATION:
   - Connect the flight computer module to the game server's tick loop
   - Connect the GUI to the flight computer via the existing server protocol
   - Ensure GUI commands → server → flight computer → physics → GUI feedback
     is a complete loop
   - Test the full flow: player clicks "intercept" on a contact in the GUI,
     flight computer computes the burn, ship moves, GUI shows progress

2. TESTING:
   - Unit tests for flight computer (burn calculations, command handling)
   - Unit tests for GUI message handling (if testable)
   - Integration test: start server, connect GUI, issue navigate command,
     verify ship moves correctly
   - Edge cases: give impossible commands, switch modes mid-burn,
     run out of fuel during maneuver

3. DOCUMENTATION:
   - Update README.md with new GUI controls and keyboard shortcuts
   - Create FLIGHT-COMPUTER.md explaining the abstraction layer:
     what commands exist, how they work, how to add new ones
   - Create GUI-GUIDE.md: player-facing explanation of the interface
   - Update CHANGELOG.md

COORDINATION RULES:
- Flight Computer Engineer starts FIRST — build the module and its interface
  before the GUI tries to talk to it
- GUI Architect can start assessing the current GUI immediately, but wait
  for the flight computer interface to be defined before wiring up commands
- GUI Architect should message Flight Computer Engineer to agree on the
  command/response format before implementing
- Integration & QA starts once the other two have initial implementations
- All teammates: if you find something in the existing code that's confusing
  or seems wrong, flag it — don't silently work around it
- All teammates: check that the server still starts cleanly after your changes

When all teammates are done, give me:
1. Summary of everything that was built/changed
2. The flight computer command interface (what commands exist, what they do)
3. GUI layout description and keyboard shortcuts
4. Test results
5. Any design questions that need my input
6. What to commit and in what order
7. Known issues or things punted to next sprint

Do NOT auto-commit. I review everything first.

===
