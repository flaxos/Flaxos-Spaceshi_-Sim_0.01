# Flaxos Spaceship Simulator - Architecture Documentation

**Version**: 0.2.0
**Last Updated**: 2026-01-20

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Architecture](#core-architecture)
3. [Module Details](#module-details)
4. [Data Flow](#data-flow)
5. [Network Protocol](#network-protocol)
6. [Station System](#station-system)
7. [Fleet System](#fleet-system)
8. [Extension Points](#extension-points)
9. [Physics Update Notes (S3)](#physics-update-notes-s3)

---

## System Overview

Flaxos Spaceship Simulator is a **hard sci-fi multiplayer space combat simulator** designed around:

- **Newtonian physics** - Realistic orbital mechanics and kinematics
- **Multi-crew stations** - Multiple players controlling different ship systems
- **Fleet coordination** - Multi-ship tactical gameplay
- **Deterministic simulation** - Consistent physics with fixed timestep
- **Client-server architecture** - TCP JSON protocol for network play

### Design Principles

1. **Separation of Concerns**: Physics, networking, and UI are isolated
2. **Modularity**: Systems are independently testable and composable
3. **Determinism**: Same inputs always produce same outputs
4. **Android Compatibility**: Core simulation runs on Pydroid3
5. **Minimal Dependencies**: NumPy optional, no heavy frameworks

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Mobile UI    │  │ Desktop GUI  │  │ Custom Client│      │
│  │ (Flask/HTML) │  │ (Tkinter)    │  │ (TCP JSON)   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
          └──────────────────┴──────────────────┘
                             │
                    TCP JSON Protocol
                             │
┌─────────────────────────────┼─────────────────────────────────┐
│                    Server Layer                                │
│  ┌──────────────────────────▼────────────────────────────┐   │
│  │         StationServer (server/station_server.py)       │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │  Station Manager    │  Telemetry Filter         │  │   │
│  │  │  Command Dispatcher │  Event Filter             │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └───────────────────────┬──────────────────────────────┘   │
└────────────────────────────┼──────────────────────────────────┘
                             │
┌─────────────────────────────┼─────────────────────────────────┐
│                   Simulation Layer                             │
│  ┌──────────────────────────▼────────────────────────────┐   │
│  │         HybridRunner (hybrid_runner.py)                │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │  Simulator          │  Ship Factory             │  │   │
│  │  │  Fleet Manager      │  Event Bus                │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └───────────────────────┬──────────────────────────────┘   │
└────────────────────────────┼──────────────────────────────────┘
                             │
┌─────────────────────────────┼─────────────────────────────────┐
│                      Ship Layer                                │
│  ┌──────────────────────────▼────────────────────────────┐   │
│  │              Ship (hybrid/ship.py)                     │   │
│  │  ┌─────────────────────────────────────────────────┐  │   │
│  │  │  Physics State      │  Command Handler          │  │   │
│  │  │  Systems            │  Telemetry Generator      │  │   │
│  │  └─────────────────────────────────────────────────┘  │   │
│  └───────────────────────┬──────────────────────────────┘   │
└────────────────────────────┼──────────────────────────────────┘
                             │
┌─────────────────────────────┼─────────────────────────────────┐
│                    Systems Layer                               │
│  ┌──────────────┬───────────┴────────┬─────────────────────┐ │
│  │ Propulsion   │ Weapons            │ Sensors             │ │
│  │ Navigation   │ Targeting          │ Power Management    │ │
│  │ Helm         │ Autopilot          │ Crew Efficiency     │ │
│  └──────────────┴────────────────────┴─────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## Module Details

### 1. Server Layer (`server/`)

#### `station_server.py` - Main Server
**Responsibilities:**
- Accept TCP client connections
- Route commands to simulation
- Filter telemetry/events by station
- Manage client sessions

**Key Components:**
- `StationServer` - Main server class
- `handle_connection()` - Per-client connection handler
- `dispatch()` - Command routing
- `_handle_get_state()` - Telemetry delivery with filtering
- `_handle_get_events()` - Event delivery with filtering
- `list_ships` command exposes live ship metadata from the simulator

#### `stations/` - Station Management System

**station_types.py**
```python
# Defines station types and permissions
StationType = CAPTAIN | HELM | TACTICAL | OPS | ENGINEERING | COMMS | FLEET_COMMANDER
PermissionLevel = OBSERVER | CREW | OFFICER | CAPTAIN

# Maps commands to stations
STATION_DEFINITIONS[station_type] = {
    "commands": set(),     # Commands this station can issue
    "displays": set(),     # Telemetry views available
    "can_override": set(), # Stations this can override
}
```

**station_manager.py**
```python
class StationManager:
    """Manages station claims and client sessions"""

    # Core operations
    register_client(client_id, player_name)
    assign_to_ship(client_id, ship_id)
    claim_station(client_id, ship_id, station)
    release_station(client_id, ship_id, station)

    # Claims auto-upgrade CAPTAIN station permissions

    # Permission checking
    can_issue_command(client_id, ship_id, command) -> (bool, str)

    # Session management
    cleanup_stale_claims() -> List[client_id]
```

**station_dispatch.py**
```python
class StationAwareDispatcher:
    """Routes commands with permission enforcement"""

    register_command(command, handler, ...)
    dispatch(client_id, ship_id, command, args) -> CommandResult
    get_available_commands(client_id) -> Dict
```

**station_commands.py**
```python
# Station management commands
register_station_commands(dispatcher, station_manager, crew_manager, ship_provider)

# list_ships returns live ship IDs + metadata from ship_provider
# transfer_station requires OFFICER or CAPTAIN permissions
```

**station_telemetry.py**
```python
class StationTelemetryFilter:
    """Filters telemetry by station permissions"""

    filter_ship_telemetry(ship_data, station) -> filtered_data
    filter_telemetry_for_client(client_id, full_snapshot) -> filtered_snapshot
```

**telemetry/station_filter.py**
```python
# Stable import path for station telemetry filtering
from server.stations.station_telemetry import StationTelemetryFilter
```

**fleet_commands.py**
```python
# Fleet coordination commands
register_fleet_commands(dispatcher, station_manager, fleet_manager)

# Commands: fleet_create, fleet_form, fleet_fire, fleet_status, etc.
```

**crew_system.py**
```python
class CrewManager:
    """Manages crew members with skills and fatigue"""

    create_crew(crew_id, name, skills)
    assign_to_ship(crew_id, ship_id, station)
    update_fatigue(crew_id, duty_hours)
    calculate_efficiency(crew_id) -> float
```

---

### 2. Simulation Layer (`hybrid/`)

#### `simulator.py` - Core Simulation
**Responsibilities:**
- Run physics tick loop
- Manage ship collection
- Process projectiles and collisions
- Publish internal events (event delivery to clients is not yet wired)

**Key Methods:**
```python
class Simulator:
    def tick(self):
        """Advance simulation by one fixed timestep (dt)"""
        # 1. Update all ships
        for ship in self.ships.values():
            ship.tick(self.dt, list(self.ships.values()), self.time)

        # 2. Update projectiles
        self._update_projectiles(dt)

        # 3. Check collisions
        self._check_collisions()

        # 4. Update formations
        self.fleet_manager.update(self.dt)

        self.time += self.dt
```

#### `ship.py` - Ship Entity
**Core State:**
```python
class Ship:
    # Physics state
    position: np.ndarray      # [x, y, z] meters
    velocity: np.ndarray      # [vx, vy, vy] m/s
    orientation: Dict         # pitch, yaw, roll (degrees)
    angular_velocity: Dict    # Rotation rates

    # Mass and propulsion
    mass: float               # kg
    fuel: float               # kg
    thrust_magnitude: float   # Current thrust (0-1)

    # Systems
    systems: Dict[str, System]

    # Combat
    weapons: List[Hardpoint]
    target_id: Optional[str]
```

**Key Methods:**
```python
def tick(self, dt: float, all_ships: list, sim_time: float):
    """Update systems, then update physics"""
    for system in self.systems.values():
        system.tick(dt, self, self.event_bus)
    self._update_physics(dt)

def handle_command(self, command_data: dict):
    """Process command"""
    return route_command(self, command_data)
```

---

### 3. Systems Layer (`hybrid/systems/`)

#### Navigation System
```python
class NavigationSystem:
    """Manages flight control and autopilot"""

    # Components
    navigation_controller: NavigationController
    autopilot_programs: Dict[str, AutopilotProgram]

    # Modes
    MANUAL, AUTOPILOT, MANUAL_OVERRIDE
```

**Autopilot Programs** (`hybrid/navigation/autopilot/`):
- `match_velocity.py` - PID velocity matching
- `intercept.py` - Lead pursuit intercept (3-phase)
- `hold.py` - Station keeping
- `formation.py` - Fleet formation maintenance

#### Weapon System
```python
class WeaponSystem:
    """Manages all ship weapons"""

    hardpoints: List[Hardpoint]

    def fire(self, hardpoint_id: str, target_id: str) -> bool
    def get_firing_solution(self, target_id: str) -> Dict
```

**Hardpoint Types**:
- Torpedoes/Missiles - Guided, PN guidance
- Railguns - Kinetic projectiles
- PDC - Point defense cannons

#### Sensor System
```python
class SensorSystem:
    """Manages passive and active detection"""

    passive: PassiveSensor    # Continuous scanning
    active: ActiveSensor      # Manual ping
    contacts: List[Contact]   # Tracked contacts

    def update_passive(self, dt: float, all_ships: Dict)
    def ping(self, all_ships: Dict)
    def get_contact(self, contact_id: str) -> Optional[Contact]
```

**Contact Lifecycle**:
1. Detection → Unknown contact (C001)
2. Classification → Small/Medium/Large
3. Identification → Full ship class
4. Aging → Confidence decay over time
5. Pruning → Remove stale contacts

#### Power System
```python
class PowerSystem:
    """Power generation and distribution"""

    reactor: Reactor
    batteries: float          # kW capacity

    def generate_power(self, dt: float) -> float
    def consume_power(self, amount: float) -> bool
```

---

## Data Flow

### Command Flow
```
Client → TCP → StationServer → Dispatcher → Ship → System → Response
  ↓                               ↓                    ↓
Session                    Permission Check      State Change
  ↓                               ↓                    ↓
Station                      Allow/Deny          Update Physics
```

### Telemetry Flow
```
Ship → get_ship_telemetry() → TelemetryFilter → Client
  ↓                                   ↓              ↓
Full State                    Station Filtering   Filtered State
```

### Event Flow
```
System → Event Bus (in-process)
  ↓
Generate internal events

Note: The TCP servers expose `get_events`, but the simulator does not currently maintain a persistent event log for clients, so event delivery is typically empty.
```

---

## Network Protocol

### Wire Format
**Newline-delimited JSON over TCP**

```
{"cmd": "claim_station", "station": "helm"}\n
{"cmd": "set_thrust", "thrust": 0.5}\n
{"cmd": "get_state"}\n
```

### Command Structure
```json
{
  "cmd": "command_name",
  "arg1": "value1",
  "arg2": 123
}
```

### Response Structure
```json
{
  "ok": true,
  "message": "Success message",
  "response": {
    "data_field": "value"
  }
}
```

### Error Response
```json
{
  "ok": false,
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

---

## Station System

### Architecture Principles

1. **Claim-Based Access**: Clients must claim a station before issuing commands
2. **Permission Enforcement**: Dispatcher checks station permissions before execution
3. **Data Filtering**: Telemetry filtered to show only relevant data per station
4. **Session Tracking**: Heartbeat system prevents stale claims

### Station Workflow

```
1. Connect → TCP connection established
2. Register → Auto-registered with client_id
3. Assign → assign_to_ship command
4. Claim → claim_station command
5. Control → Issue station-specific commands
6. View → Receive filtered telemetry
7. Release → release_station or disconnect
```

### Permission Matrix

| Station | Commands | Telemetry | Can Override |
|---------|----------|-----------|--------------|
| CAPTAIN | All | All | All stations |
| HELM | Navigation, propulsion | Nav, position, fuel | - |
| TACTICAL | Weapons, targeting | Weapons, targets | - |
| OPS | Sensors, ECM | Sensors, contacts | - |
| ENGINEERING | Power, repairs | Systems, damage | - |
| COMMS | Communication, IFF | Comms, fleet | - |
| FLEET_COMMANDER | Fleet coordination | Fleet status, tactics | TACTICAL, COMMS |

---

## Fleet System

### Fleet Manager
```python
class FleetManager:
    """Manages fleet formations and coordination"""

    fleets: Dict[str, Fleet]

    def create_fleet(self, fleet_id: str, name: str, flagship_id: str, ship_ids: list[str] | None = None)
    def add_ship_to_fleet(self, ship_id: str, fleet_id: str)
    def form_fleet(self, fleet_id: str, formation_type: str, spacing: float = 2000.0)
    def update(self, dt: float)  # Maintain formations
```

### Formation Types
- **LINE** - Ships in a line abreast
- **WEDGE** - V-shaped formation
- **COLUMN** - Single file
- **SPHERE** - 3D defensive sphere

### Formation Calculation
```python
def calculate_position(ship_index: int, formation_type: str, spacing: float):
    """Calculate formation position for ship"""
    # Returns offset from fleet center
    return np.array([x, y, z])
```

---

## Extension Points

### Adding New Systems

1. **Create System Class** (`hybrid/systems/new_system.py`)
```python
class NewSystem:
    def __init__(self, ship):
        self.ship = ship

    def tick(self, dt: float, ship, event_bus):
        """Called each physics tick"""
        pass

    def get_telemetry(self) -> Dict:
        """Return system state"""
        return {}
```

2. **Register in Ship** (`hybrid/ship.py`)
```python
self.systems["new_system"] = NewSystem(self)
```

3. **Add Commands** (`hybrid/commands/new_commands.py`)
```python
def handle_new_command(ship, args):
    ship.systems["new_system"].do_something()
    return {"ok": True}
```

### Adding New Stations

1. **Define Station** (`server/stations/station_types.py`)
```python
class StationType(Enum):
    NEW_STATION = "new_station"

STATION_DEFINITIONS[StationType.NEW_STATION] = StationDefinition(
    station_type=StationType.NEW_STATION,
    commands={"command1", "command2"},
    displays={"display1", "display2"},
)
```

2. **Add Telemetry Mapping** (`server/stations/station_telemetry.py`)
```python
self.display_field_mapping["display1"] = ["field1", "field2"]
```

### Adding New Commands

1. **Create Handler** (`server/stations/station_commands.py`)
```python
def handle_new_command(client_id: str, ship_id: str, args: Dict) -> CommandResult:
    # Implementation
    return CommandResult(success=True, message="Done")
```

2. **Register Command** (`server/stations/station_commands.py`)
```python
dispatcher.register_command(
    command="new_command",
    handler=handle_new_command,
    station=StationType.NEW_STATION
)
```

---

## Physics Update Notes (S3)

Sprint S3 introduces quaternion-based attitude representation and torque-driven angular dynamics. The new physics flow keeps Euler angles for telemetry and commands but stores the authoritative attitude state as a normalized quaternion. RCS thrusters will generate torque that feeds angular acceleration, replacing direct Euler velocity updates.

For implementation details, integration sketches, and rollout checklists, see `docs/PHYSICS_UPDATE.md`.

---

## Performance Considerations

### Physics Tick Rate
- **Default**: 10 Hz (dt=0.1s)
- **Deterministic**: Fixed timestep for consistency
- **Scalability**: Tested with 10 ships at 10Hz

### Network Optimization
- **Telemetry Filtering**: Reduces bandwidth by ~60%
- **Event Filtering**: Only relevant events sent
- **Delta Compression**: Could be added for further optimization

### Memory Management
- **Contact Pruning**: Old contacts removed automatically
- **Event Log**: Limited to last 100 events
- **Projectile Cleanup**: Removed when out of range

---

## Testing Architecture

### Test Layers
1. **Unit Tests** - Individual functions/classes
2. **Integration Tests** - System interactions
3. **Hybrid Tests** - Full simulation scenarios

### Test Organization
```
tests/
├── core/              # Event bus, utilities
├── systems/           # Individual systems
│   ├── power/
│   ├── weapons/
│   ├── sensors/
│   └── navigation/
├── stations/          # Station system tests
├── hybrid_tests/      # Full integration
└── phase2/            # Phase 2 features
```

---

## Directory Structure

```
Flaxos-Spaceshi_-Sim_0.01/
├── hybrid/                  # Core simulation
│   ├── ship.py             # Ship entity
│   ├── simulator.py        # Main simulator
│   ├── ship_factory.py     # Ship creation
│   ├── systems/            # Ship systems
│   │   ├── weapons/
│   │   ├── sensors/
│   │   ├── navigation/
│   │   └── power/
│   ├── fleet/              # Fleet management
│   ├── scenarios/          # Mission system
│   ├── navigation/         # Autopilot
│   └── commands/           # Command handlers
├── server/                 # Network server
│   ├── station_server.py   # Main server
│   ├── run_server.py       # Launcher
│   └── stations/           # Station system
│       ├── station_types.py
│       ├── station_manager.py
│       ├── station_dispatch.py
│       ├── station_telemetry.py
│       ├── station_commands.py
│       ├── fleet_commands.py
│       └── crew_system.py
├── tests/                  # Test suites
├── docs/                   # Documentation
├── scenarios/              # YAML scenarios
├── hybrid_fleet/           # Ship definitions
└── mobile_ui/              # Android UI
```

---

## Future Architecture Changes

### Sprint S3: Quaternion Attitude
- Add `hybrid/utils/quaternion.py`
- Replace `Ship.orientation` dict with `Ship.quaternion`
- Update physics integration to use quaternion derivatives
- Document quaternion usage in `docs/QUATERNION_API.md`
- Define RCS configuration format in `docs/RCS_CONFIGURATION_GUIDE.md`

### Sprint S4: Damage Model
- Add `hybrid/systems/damage/` module
- Per-subsystem health tracking
- Damage propagation logic

### Sprint S6: Network Robustness
- Connection pooling
- Auto-reconnect logic
- Bandwidth monitoring
- Delta compression for telemetry

---

**Document Status**: Complete
**Maintained By**: Development Team
**Review Frequency**: After architectural changes
