GUIDE.md

🛰️ Developer Guide

Project Structure

core/: Contains critical simulation modules including command processing, propulsion control, and simulation mechanics.

fleet/: Manages fleet configuration and state definitions.

hybrid/: Handles hybrid propulsion system logic.

scenarios/: Defines scenarios for simulation testing.

utils/: Provides utility functions supporting the core modules.

Core Components

Command Server (command_server.py): Central command routing and handling for simulation.

RCS Controller (rcs_controller.py): Manages Reaction Control Systems for spacecraft maneuvering.

Base Systems (base_system.py): Fundamental class structure and interfaces for various ship systems.

Scenario Management

Scenarios are defined in JSON format specifying initial conditions, targets, and objectives:

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

Extending the Simulator

Adding New Modules:

Create new Python files within the appropriate directories (core, fleet, etc.).

Ensure modules follow clear and consistent interfaces.

Testing:

Implement tests within a new or existing test directory.

Write unit and integration tests to validate functionality.

Pull Requests:

Clearly document all changes in pull requests.

Maintain consistent coding style and include comprehensive comments.

Design Philosophy

Modularity: Components should be independent and interchangeable.

Realism with Flexibility: Realistic physics and logic balanced with gameplay-friendly adjustments.

Scalability: Easy to extend and manage multiple ships and scenarios.
