# 🛰️ Developer Guide

This guide provides an overview of the project layout and explains how to extend or run the Flaxos Spaceship Simulator.

## Project Structure

- **`core/`** – foundational utilities such as `command.py` and math helpers used across the project.
- **`cli/`** – small command line helpers (for example `power_demo.py`).
- **`hybrid/`** – primary implementation of ship systems and the event‑driven simulator.
  - `systems/` – contains modular subsystems including the power manager, navigation and sensors.
  - `ship.py` – object representing a single ship composed of systems.
  - `simulator.py` – runs the hybrid event loop and orchestrates ship updates.
- **`scenarios/`** – JSON/YAML scenario files for loading predefined fleets.
- **`fleet/`** – sample ship definitions.
- **`gui_control.py` / `simple_gui.py`** – Tkinter interfaces for visual interaction.

## Core Components

- **Command Server (`command_server.py`)** – routes CLI or GUI actions to individual ships.
- **Power Management System** – layered reactors defined in `hybrid/systems/power_management_system.py`.
- **Navigation System** – autopilot, waypoint handling and thrust limits (`hybrid/systems/navigation_system.py`).
- **Simulation Loop (`simulation.py`)** – updates ship physics each tick.
- **RCS Controller (`rcs_controller.py`)** – handles reaction control thrusters.

## Scenario Format

Scenarios are JSON files specifying starting conditions and objectives. A minimal example:
```json
{
  "scenario_id": "example_001",
  "ships": [
    {
      "id": "ship_alpha",
      "initial_state": {
        "position": {"x": 0, "y": 0, "z": 0},
        "velocity": {"x": 0, "y": 0, "z": 0}
      }
    }
  ],
  "objectives": ["reach_waypoint", "engage_target"]
}
```
Place scenario files in the `scenarios/` directory and load them using the CLI or GUI.

## Extending the Simulator

1. **Add a new subsystem** by creating a Python module in `hybrid/systems/` that subclasses `BaseSystem` and implements the `tick`, `command` and `get_state` methods.
2. **Update ship configurations** in `fleet/` to include the new subsystem under the `systems` section.
3. **Run tests** in `hybrid/tests/` or add new ones with `unittest`.

Unit tests can be executed with:
```bash
pytest
```

## Design Philosophy

- **Modularity** – each system is self contained and communicates via the event bus.
- **Realistic but Playable Physics** – thrust, inertia and sensor ranges are simulated using simplified equations for ease of experimentation.
- **Scalability** – multiple ships and scenarios can run in parallel using the simulator or the command server.

