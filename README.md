# 🚀 Flaxos Spaceship Simulator

## Project Overview

Flaxos Spaceship Simulator is a modular Python project for experimenting with realistic spaceship mechanics. A small event bus allows loosely coupled systems while both CLI and GUI front‑ends drive the simulation.

## Folder Structure

```
hybrid/
  core/           # base classes, event bus and constants
  systems/
    power/       # reactor and power management
    weapons/     # weapon logic and hardpoints
    navigation/  # navigation system
    sensors/     # sensor system
  cli/           # command line entry point
  gui/           # GUI entry point
```

Tests live under `tests/` with the same layout.

## Installation

1. Install **Python 3.10+**.
2. Clone the repository:
   ```bash
   git clone https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01.git
   cd Flaxos-Spaceshi_-Sim_0.01
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running

Run the CLI simulation:
```bash
python -m hybrid.cli.run_cli --config path/to/ships.json
```

Launch the GUI:
```bash
python -m hybrid.gui.run_gui
```

The unified GUI loads scenarios, starts the simulation server and exposes
navigation, helm, sensors and power controls. A placeholder panel for weapons is
included for future work. The new power management system models reactor
ramp‑up, thermal limits and failover. Weapons will draw power via the management
system and build heat over time.

## Roadmap

Upcoming work includes launch bay mechanics, hierarchical ship components, fleet‑level scaling and richer GUI controls.
