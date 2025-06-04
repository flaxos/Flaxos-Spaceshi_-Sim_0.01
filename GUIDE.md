# 🛰️ Developer Guide

This guide explains the project layout and how to extend the simulator.

## Structure

- **`hybrid/core/`** – shared modules: `base_system.py`, `event_bus.py` and `constants.py`.
- **`hybrid/systems/`** – subsystem packages such as power, weapons, navigation and sensors.
- **`hybrid/cli/`** & **`hybrid/gui/`** – entry points for text and graphical control.
- **`tests/`** – unit tests mirroring the package layout.

Ships are created via helper functions in `hybrid/ship_factory.py` which assemble reactors, weapons and navigation components using definitions from JSON files.

## Adding Reactors or Weapons

To introduce a new reactor type, subclass `Reactor` in `hybrid/systems/power/reactor.py` and supply any specialised behaviour. Register it in ship configuration when building `PowerManagementSystem`.

New weapons can be created by subclassing `Weapon` in `hybrid/systems/weapons/weapon_system.py`. Mount them on `Hardpoint` objects in the ship config.

## Extending the Simulator

Future modules such as launch bays, ship hierarchy handling or fleet management should be placed under `hybrid/systems/` in a dedicated subpackage. The `Simulation` class in `hybrid/systems/simulation.py` can be expanded to manage multiple fleets or more complex event logic.

Run unit tests with:
```bash
pytest
```
