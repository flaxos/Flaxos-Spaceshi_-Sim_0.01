# Spaceship Simulator

## Overview
A Python-based spaceship simulator featuring:
- Modular OOP/event-driven design
- Layered reactor power management (primary, secondary, tertiary)
- Weapon and hardpoint systems with power checks, heat, and cooldown

## Folder Structure
hybrid/
core/
event_bus.py
base_system.py
constants.py
systems/
power/
reactor.py
management.py
weapons/
weapon_system.py
hardpoint.py
navigation/
navigation.py
sensors/
sensor_system.py
simulation.py
cli/
run_cli.py
gui/
run_gui.py
tests/
core/
test_event_bus.py
systems/
power/
test_reactor.py
test_management.py
weapons/
test_weapon_system.py
test_hardpoint.py
hybrid_tests/
test_ship_initialization.py

## Installation
1. Create a virtual environment (Python 3.8+ recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate   # (Windows: venv\Scripts\activate)
   ```
Install dependencies (if any):
```bash
pip install -r requirements.txt
```

## Usage
### CLI
```bash
python -m hybrid.cli.run_cli --config path/to/ships.json --time 60
```
`--config` should be a JSON mapping each ship ID to its configuration (power, weapons, navigation, sensors).

`--time` is total simulation duration in seconds.

### GUI
```bash
python -m hybrid.gui.run_gui
```
Launches a Tkinter window. Edit hybrid/gui/run_gui.py to customize widgets.

## Core Systems
**PowerManagementSystem** (`hybrid/systems/power/management.py`)

Manages three reactors: primary, secondary, tertiary.

`tick(dt)` handles ramp-up and overheating.

`request_power(amount, consumer)` draws from reactors in priority order.

`transfer_output(src, dest, amount)` allows emergency rerouting.

**WeaponSystem** (`hybrid/systems/weapons/weapon_system.py`)

Defines Weapon class: handles cooldown, heat, ammo, and power checks.

Defines WeaponSystem to manage multiple Weapon instances.

**Hardpoint** (`hybrid/systems/weapons/hardpoint.py`)

Mounts or unmounts Weapon objects.

Delegates `fire(...)` to its mounted Weapon.

**NavigationSystem** (`hybrid/systems/navigation/navigation.py`)

Placeholder: update ship movement logic here.

**SensorSystem** (`hybrid/systems/sensors/sensor_system.py`)

Placeholder: passive/active detection logic.

**Simulation** (`hybrid/systems/simulation.py`)

Central loop that ticks sensors, navigation, weapons, and power each frame.

## Development Roadmap
Completed:

- Tick-based simulation loop
- Layered power management (ramp, thermal)
- Basic weapon and hardpoint modules
- Core EventBus for pub/sub

In Progress:

- GUI integration (Tkinter skeleton)
- Sensor gameplay loops

Pending:

- Launch bay & ship hierarchy features
- Fleet‐level scaling
- Advanced GUI controls (RCS buttons, contact panels)

## Testing
```bash
pytest --maxfail=1 -q
```
Tests cover reactor ramp/overheat, power prioritization, weapon cooldown/heat/ammo.
