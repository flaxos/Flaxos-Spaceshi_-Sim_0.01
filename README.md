# 🚀 Flaxos Spaceship Simulator

## Project Overview

Flaxos Spaceship Simulator is a Python-based project for experimenting with hard science-fiction ship mechanics. It focuses on modular subsystem design, physics-driven propulsion and a layered power model for managing ship resources. Both a command line interface and a lightweight Tkinter GUI are provided for interacting with the simulation.

## Key Implementations

- **Layered Power Management**
  - **Primary Reactor** – powers main propulsion and primary weapons.
  - **Secondary Reactor** – feeds sensors, reaction control thrusters and self‑defense systems.
  - **Tertiary Reactor** – maintains life support and crew bio‑monitoring.
- **CLI and Lightweight GUI** for issuing commands and visualising ship state.
- **Realistic Physics** calculations of thrust and inertia along with basic sensor range modelling.

## Codebase Structure

- `ship_factory.py` – builds `Ship` objects from configuration dictionaries.
- `hybrid/systems/power_management_system.py` – implements the three‑reactor power manager.
- `simulation.py` – core loop updating position, orientation and running system ticks.
- `hybrid/systems/navigation_system.py` – autopilot logic and course following.
- `command_server.py` – central command routing for the CLI/GUI.
- `simple_gui.py` – minimal Tkinter interface for monitoring a single ship.

File interdependencies are straightforward: `simulation.py` drives per‑tick updates and calls into systems defined under `hybrid/systems`. Ships are created via `ship_factory.py`, which attaches these systems to a `Ship` instance. The CLI and GUI front ends issue commands that flow through `command_server.py` to the relevant ship systems.

## Installation

1. Install **Python 3.10+**.
2. Clone the repository:
   ```bash
   git clone https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01.git
   cd Flaxos-Spaceshi_-Sim_0.01
   ```
3. Install dependencies (numpy, pyyaml, tkinter is included with most Python distributions):
   ```bash
   pip install numpy pyyaml
   ```

## Usage

Run the main simulation server:
```bash
python core/command_server.py
```

Start a simple GUI:
```bash
python simple_gui.py
```

To experiment with the power system via CLI:
```bash
python cli/power_demo.py status
python cli/power_demo.py request --amount 10 --system propulsion
python cli/power_demo.py reroute --amount 5 --from_layer primary --to_layer secondary
```

## Deployment Details

Power management is integrated as a standard system. When a ship configuration includes a `power_management` block the GUI's power panel becomes active. The system resets reactor output every tick and raises events if a layer falls below the configured threshold. Status and rerouting commands can be issued from either the CLI or GUI, allowing live monitoring of available power during a run.

## Future Roadmap

Planned improvements include:
- Advanced sensor gameplay loops with active pings and contact tracking.
- Multiplayer and fleet interactions across networked simulations.
- Expanded GUI with richer status displays and command controls.
- Additional modular subsystems such as launch bays and improved weapons.

Contributions are welcome! Fork the repository, create a feature branch and open a pull request with your changes.
