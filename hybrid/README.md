# Hybrid Ship Simulation Architecture

This folder contains a hybrid object-oriented and event-driven architecture for the ship simulation. It's designed to be modular, extensible, and easy to maintain.

## Core Components

### BaseSystem
The foundation of the architecture is the `BaseSystem` class, which defines the interface that all ship systems must implement. It includes methods for:
- Initialization with configuration
- Updating system state during simulation ticks
- Processing commands
- Returning system state

### EventBus
The `EventBus` provides loose coupling between systems, allowing them to communicate without direct dependencies. Systems can:
- Publish events with associated data
- Subscribe to events from other systems
- React to events in a decoupled way

### Ship
The `Ship` class manages multiple systems and handles physics simulation. It:
- Initializes systems based on configuration
- Updates systems during simulation ticks
- Routes commands to appropriate systems
- Tracks position, velocity, orientation, etc.

## System Implementations

The architecture includes several system implementations:
- `PowerSystem`: Handles power generation, storage, and distribution
- `PropulsionSystem`: Manages main drive thrust
- `SensorSystem`: Handles active and passive sensor functionality
- `HelmSystem`: Manages manual control of ship thrust and orientation
- `NavigationSystem`: Handles autopilot and course plotting
- `BioMonitorSystem`: Tracks crew health and g-force limits

## Using the Hybrid Architecture

### Loading Ships
```python
from hybrid.simulator import Simulator

# Create a simulator
sim = Simulator()

# Load ships from JSON files
sim.load_ships_from_directory("fleet")

# Or create a ship manually
ship_config = {
    "position": {"x": 0, "y": 0, "z": 0},
    "systems": {
        "power": {"generation": 10.0, "capacity": 100.0},
        "propulsion": {"main_drive": {"max_thrust": 50.0}}
    }
}
ship = sim.add_ship("my_ship", ship_config)
