README.md

🚀 Flaxos Spaceship Simulator

Overview

The Flaxos Spaceship Simulator is a modular and extensible simulation framework designed to simulate realistic spaceship mechanics, navigation, and fleet operations. It provides a robust environment for simulating various spacecraft, propulsion systems, and sensor suites within a realistic physics environment.

Key Features

Modular Architecture: Easily extendable with separate modules for core systems, fleets, and utility functions.

Hybrid Simulation: Supports both conventional and advanced propulsion methods.

Scenario-based Testing: Predefined scenarios for testing, training, and demonstrations.

Extensible Fleet Management: Easy integration and configuration of multiple spacecraft and states.

Installation

Clone the repository:

git clone https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01.git

Navigate to the project directory:

cd Flaxos-Spaceshi_-Sim_0.01

Install required dependencies:

pip install -r requirements.txt

Usage

Start the simulation server:

python core/command_server.py

Run a scenario:

python sim/run_scenario.py --scenario scenarios/sample_scenario.json

Power Management
----------------

The simulator includes a three-layer power management system. A command-line
demo allows querying status, requesting power, and rerouting between layers:

```
python cli/power_demo.py status
python cli/power_demo.py request --amount 10 --system propulsion
python cli/power_demo.py reroute --amount 5 --from_layer primary --to_layer secondary
```

For a graphical interface, run `python simple_gui.py` and use the "Power
Management" panel to monitor reactors or issue power commands.

Example scenarios now include a basic `power_management` block. When this
system is present on a ship, the GUI panel becomes active and allows live
control. A minimal configuration looks like:

```json
"systems": {
  "propulsion": { ... },
  "power_management": {
    "primary": {"output": 100.0},
    "secondary": {"output": 50.0},
    "tertiary": {"output": 25.0},
    "system_map": {
      "propulsion": "primary",
      "sensors": "secondary"
    }
  }
}
```

Contributing

Fork the repository

Create a new branch for your feature or fix

Submit a pull request with clear descriptions and documented code

License

This project is licensed under the MIT License - see the LICENSE.md file for details.

