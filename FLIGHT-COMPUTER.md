# Flight Computer

## What It Is

The flight computer is a server-side system that sits between the player's intent
and the low-level autopilot/navigation layer. Instead of manually engaging
autopilot programs and setting parameters, the player issues high-level commands
("navigate to X", "intercept target", "evasive") and the flight computer handles
burn planning, autopilot selection, progress tracking, and status reporting.

## Why It Exists

Before the flight computer, players had to:
1. Pick the right autopilot program name
2. Supply raw parameters (target IDs, coordinates)
3. Manually check progress via navigation state

The flight computer provides:
- **Burn plans** with delta-v, fuel cost, and confidence estimates before committing
- **Progress tracking** with ETA and phase information
- **Unified command interface** for all manoeuvre types
- **Automatic abort** if the autopilot disengages unexpectedly

## Architecture

```
Player / GUI
     |
     v
CommandDispatcher  --->  flight_computer_commands.py
     |
     v
FlightComputer (BaseSystem)         <-- hybrid/systems/flight_computer/
  |-- models.py     BurnPlan, FlightComputerStatus dataclasses
  |-- planning.py   Burn estimation (goto, intercept, match, orbit)
  |-- system.py     Main system: command dispatch, tick, state
     |
     v
NavigationSystem.set_autopilot()    <-- hybrid/systems/navigation/
     |
     v
NavigationController
     |
     v
AutopilotFactory.create()          <-- hybrid/navigation/autopilot/
     |
     v
Concrete Autopilot (GoToPosition, Intercept, Hold, Orbit, Evasive, ...)
```

The flight computer is registered as `ship.systems["flight_computer"]` and
created automatically for every ship. Its `tick()` is called each frame by
the ship's update loop, and its state appears in `ship.get_state()` under
`systems.flight_computer`.

## Available Commands

All commands go through `flight_computer` with an `action` parameter:

| Action           | Parameters                                  | Description                          |
|------------------|---------------------------------------------|--------------------------------------|
| `navigate_to`    | `x`, `y`, `z`                               | Fly to coordinates and stop          |
| `intercept`      | `target` (contact ID)                       | Pursue and close on a target         |
| `match_velocity` | `target` (contact ID)                       | Zero relative velocity with target   |
| `hold_position`  | (none)                                      | Station-keep at current position     |
| `orbit`          | `center_x/y/z`, `radius`, opt. `speed`      | Circular orbit around a point        |
| `evasive`        | opt. `duration`                             | Random jink pattern                  |
| `manual`         | (none)                                      | Disengage, return to manual control  |
| `abort`          | (none)                                      | Emergency stop, kill thrust           |
| `status`         | (none)                                      | Return current flight computer state |

### Example (via command dispatcher)

```python
dispatcher.dispatch("flight_computer", ship, {
    "action": "navigate_to",
    "x": 5000, "y": 0, "z": 0,
})
```

### Example (via GUI)

The `<flight-computer-panel>` web component sends:
```javascript
wsClient.sendShipCommand("flight_computer", { action: "hold_position" });
```

## Response Format

Every command returns a dict with at least `ok` (bool). Successful manoeuvre
commands also include a `burn_plan`:

```json
{
  "ok": true,
  "status": "Autopilot engaged: goto_position",
  "burn_plan": {
    "command": "navigate_to",
    "estimated_time": 44.7,
    "fuel_cost": 12.3,
    "delta_v": 316.2,
    "confidence": 1.0,
    "phases": ["accelerate", "coast", "brake", "hold"],
    "warnings": []
  }
}
```

## How to Add a New Command

1. Add a method on `FlightComputer` in `system.py` (e.g. `def dock(self, ship, ...)`).
2. Add a planning function in `planning.py` if burn estimation is needed.
3. Register the new autopilot program in `hybrid/navigation/autopilot/factory.py`
   if a new autopilot class is required.
4. Wire it into `FlightComputer.command()` dispatch dict.
5. Add the action name to the `choices` list in `flight_computer_commands.py`.
6. Add the action to the `choices` in `validators.py` `validate_autopilot_program`
   if it should also be available as a raw autopilot command.

## Relationship to Existing Autopilot System

The flight computer does **not** replace the autopilot layer. It wraps it:

- **Autopilot** (`hybrid/navigation/autopilot/`): Low-level programs that compute
  thrust + heading each tick. They know about physics, braking distances, orbits.
- **NavigationSystem** (`hybrid/systems/navigation/`): Owns the `NavigationController`,
  applies autopilot commands to propulsion and RCS.
- **FlightComputer** (`hybrid/systems/flight_computer/`): High-level orchestrator.
  Plans burns, engages the right autopilot, tracks progress, reports status.

Players can still use the raw `autopilot` command to engage programs directly.
The flight computer is the recommended interface for the GUI.
