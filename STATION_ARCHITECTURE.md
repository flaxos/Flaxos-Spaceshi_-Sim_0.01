# Station-Based Control Architecture - Implementation Summary

## Overview

This document describes the complete implementation of the station-based control architecture for the Flaxos Spaceship Simulator. This system enables **multi-crew ship control** where multiple players can simultaneously control different stations on the same ship, similar to The Expanse TV series.

## Implementation Date

**Branch:** `claude/station-control-architecture-uIcTD`
**Status:** Phase 1 Complete
**Date:** January 2026

## Architecture Goals

✅ **Multiple clients per ship**: Different players control different stations
✅ **Station-based permissions**: Commands filtered by station role
✅ **Telemetry filtering**: Each station sees only relevant data
✅ **Session management**: Track clients, handle disconnects, auto-cleanup
✅ **Backward compatible**: Legacy commands still work
✅ **Foundation for fleet combat**: Ready for multi-ship expansion

## System Components

### 1. Core Modules

#### `server/stations/station_types.py`
Defines the six crew stations and their capabilities:

- **StationType Enum**: CAPTAIN, HELM, TACTICAL, OPS, ENGINEERING, COMMS
- **PermissionLevel Enum**: OBSERVER, CREW, OFFICER, CAPTAIN
- **StationDefinition**: Commands, displays, required systems for each station
- **STATION_DEFINITIONS**: Complete mapping of station → capabilities

Key functions:
- `get_station_commands()`: Get all commands for a station
- `get_station_for_command()`: Find which station owns a command
- `can_station_issue_command()`: Permission check

#### `server/stations/station_manager.py`
Manages client sessions and station claims:

- **StationClaim**: Represents a client's claim on a station
- **ClientSession**: Tracks connected client state
- **StationManager**: Central coordinator for all station operations

Key methods:
- `register_client()`: Register new connection
- `assign_to_ship()`: Assign client to a ship
- `claim_station()`: Claim a station on assigned ship
- `release_station()`: Release station claim
- `can_issue_command()`: Check if client can issue command
- `cleanup_stale_claims()`: Auto-cleanup inactive clients (5 min timeout)

#### `server/stations/station_dispatch.py`
Routes commands with permission enforcement:

- **CommandResult**: Standardized command response format
- **StationAwareDispatcher**: Main command routing with permission checks
- **Legacy command wrapper**: Integrates with existing command system

Key methods:
- `register_command()`: Register command handler with metadata
- `dispatch()`: Route command with permission check
- `create_legacy_command_wrapper()`: Wrap existing command handlers

#### `server/stations/station_telemetry.py`
Filters telemetry data by station:

- **StationTelemetryFilter**: Main filtering engine
- **Display field mapping**: Maps station displays → telemetry fields

Key methods:
- `filter_ship_telemetry()`: Filter ship data for a station
- `filter_telemetry_for_client()`: Filter full snapshot for client
- `create_station_specific_telemetry()`: Create optimized view for station

#### `server/stations/station_commands.py`
Station management command handlers:

Commands:
- `register_client`: Auto-called on connection
- `assign_ship`: Join a ship
- `claim_station`: Claim a station
- `release_station`: Release current station
- `station_status`: View all stations on ship
- `my_status`: View own session status
- `fleet_status`: View all ships and crews
- `heartbeat`: Keep session alive
- `list_ships`: List available ships

#### `server/station_server.py`
Enhanced TCP server with station support:

- **StationServer**: Main server class
- Integrates all station components
- Handles client lifecycle (connect, disconnect, cleanup)
- Routes commands through station dispatcher
- Filters telemetry based on station

### 2. Station Definitions

#### CAPTAIN Station
- **Authority**: Can issue ANY command, override any station
- **Commands**: All commands + captain-specific (alert_status, override, etc.)
- **Displays**: Full telemetry
- **Can Override**: All stations

#### HELM Station
- **Role**: Navigation and flight control
- **Commands**:
  - Flight: set_thrust, heading, pitch, yaw, roll
  - Autopilot: autopilot, set_course, autopilot_hold
  - Docking: dock_initiate, undock, request_docking
- **Displays**: Position, velocity, orientation, fuel, autopilot status
- **Required Systems**: propulsion, helm, navigation

#### TACTICAL Station
- **Role**: Weapons and targeting
- **Commands**:
  - Targeting: target, untarget, target_nearest
  - Weapons: fire, fire_torpedo, fire_pdc, fire_railgun
  - PDC: pdc_mode, pdc_auto, pdc_manual
  - Solutions: compute_solution, lock_solution
- **Displays**: Weapons status, target info, firing solutions, ammunition
- **Required Systems**: weapons, targeting

#### OPS Station
- **Role**: Sensors and electronic warfare
- **Commands**:
  - Sensors: ping_sensors, scan, set_sensor_mode
  - Contacts: contacts, classify, track, track_all
  - ECM: ecm_on, eccm_on, jam, spoof
- **Displays**: Contacts, sensor status, signature analysis, detection log
- **Required Systems**: sensors

#### ENGINEERING Station
- **Role**: Power and damage control
- **Commands**:
  - Power: power_allocate, reactor_level, set_power
  - Damage: repair, damage_report, seal_compartment
  - Systems: power_on, power_off, restart_system
  - Fuel: refuel, transfer_fuel
- **Displays**: Power grid, system status, damage reports, fuel status
- **Required Systems**: power, power_management

#### COMMS Station
- **Role**: Fleet coordination and communication
- **Commands**:
  - Comms: hail, broadcast, tightbeam
  - Fleet: fleet_order, request_support
  - IFF: iff_interrogate, iff_respond
  - Jamming: comm_jam
- **Displays**: Comm log, fleet status, message queue, IFF contacts
- **Required Systems**: comms

## Client Workflow

### 1. Connection
```
Client → TCP Connect → StationServer
  ↓
Auto-register with StationManager
  ↓
Receive welcome message with client_id
```

### 2. Ship Assignment
```json
{"cmd": "assign_ship", "ship": "test_ship_001"}
→ {"ok": true, "message": "Assigned to ship test_ship_001"}
```

### 3. Station Claim
```json
{"cmd": "claim_station", "station": "helm"}
→ {
    "ok": true,
    "message": "Station helm claimed successfully",
    "response": {
      "station": "helm",
      "available_commands": [...]
    }
  }
```

### 4. Command Execution
```json
{"cmd": "set_thrust", "x": 100, "y": 0, "z": 0}
→ Permission check → Execute → Return result
```

### 5. State Query
```json
{"cmd": "get_state", "ship": "test_ship_001"}
→ Get telemetry → Filter by station → Return filtered data
```

## Permission System

### Permission Flow
```
Command received
  ↓
Check client session
  ↓
Check station claim
  ↓
Get station's available commands
  ↓
Command in allowed list?
  ├─ YES → Execute command
  └─ NO → Return permission denied
```

### Permission Denied Example
```json
// HELM trying to fire weapons
{"cmd": "fire"}
→ {"ok": false, "message": "Permission denied: Command 'fire' requires tactical station"}
```

## Telemetry Filtering

### Display Field Mapping
Each station's displays map to specific telemetry fields:

**HELM displays:**
- `nav_status` → position, velocity, orientation
- `fuel_status` → fuel, delta_v_remaining
- `autopilot_status` → nav_mode, autopilot_program

**TACTICAL displays:**
- `weapons_status` → weapons
- `target_info` → target_id
- `ammunition` → weapons.ammunition

**OPS displays:**
- `contacts` → sensors.contacts
- `sensor_status` → sensors, systems.sensors

### Filtered Output Example

**Full telemetry (Captain sees):**
```json
{
  "id": "test_ship_001",
  "position": {...},
  "velocity": {...},
  "weapons": {...},
  "sensors": {...},
  "systems": {...}
}
```

**Filtered for HELM:**
```json
{
  "id": "test_ship_001",
  "position": {...},
  "velocity": {...},
  "fuel": {...},
  "nav_mode": "manual"
}
```

**Filtered for TACTICAL:**
```json
{
  "id": "test_ship_001",
  "weapons": {...},
  "target_id": "enemy_probe",
  "orientation": {...}
}
```

## Session Management

### Lifecycle
1. **Connect**: Auto-register, assign client_id
2. **Assign**: Client chooses ship
3. **Claim**: Client claims station
4. **Active**: Issue commands, receive telemetry
5. **Heartbeat**: Periodic activity updates
6. **Disconnect**: Auto-release claims, cleanup session

### Timeout & Cleanup
- **Heartbeat timeout**: 5 minutes
- **Auto-cleanup**: Stale sessions removed automatically
- **Reconnect**: Must re-claim station

### Claim Rules
- ✅ One station per client (configurable)
- ✅ One client per station
- ✅ Must be assigned to ship first
- ✅ Station released on disconnect
- ✅ Captain can force-release stations

## Integration with Existing System

### Backward Compatibility
The station system wraps the existing command handler:

```python
# Old system (still works)
route_command(ship, command_data)

# New system (with permissions)
dispatcher.dispatch(client_id, ship_id, command, args)
  ↓
Check permissions
  ↓
Call legacy route_command()
```

### Legacy Command Mapping
All existing commands automatically mapped to stations:
- `set_thrust` → HELM
- `ping_sensors` → OPS
- `fire` → TACTICAL
- etc.

## Running the System

### Start Station-Enabled Server
```bash
python -m server.station_server --host 0.0.0.0 --port 8765 --dt 0.1 --fleet-dir hybrid_fleet
```

### Test Client
```bash
python test_station_client.py        # Basic workflow test
python test_station_client.py multi  # Multi-station test
```

### Manual Test (netcat)
```bash
nc localhost 8765
{"cmd": "assign_ship", "ship": "test_ship_001"}
{"cmd": "claim_station", "station": "helm"}
{"cmd": "set_thrust", "x": 100, "y": 0, "z": 0}
{"cmd": "get_state", "ship": "test_ship_001"}
```

## Files Created

```
server/
├── stations/
│   ├── __init__.py              # Package exports
│   ├── station_types.py         # Station definitions (267 lines)
│   ├── station_manager.py       # Session & claim management (376 lines)
│   ├── station_dispatch.py      # Command routing (257 lines)
│   ├── station_telemetry.py     # Telemetry filtering (287 lines)
│   ├── station_commands.py      # Management commands (315 lines)
│   └── README.md                # User documentation
├── station_server.py            # Enhanced TCP server (339 lines)
test_station_client.py           # Test client (283 lines)
STATION_ARCHITECTURE.md          # This document
```

**Total new code: ~2,100 lines**

## Testing Results

✅ **Module imports**: All modules import successfully
✅ **Station manager**: Client registration, ship assignment, station claims working
✅ **Command routing**: Permission checks functioning correctly
✅ **Telemetry filtering**: Filtered output generated correctly
✅ **Server startup**: Station server initializes and listens

## Next Steps (Phase 2)

### Multi-Ship Fleet Combat
- [ ] Fleet formation commands
- [ ] Inter-ship coordination
- [ ] Fleet-level tactical view
- [ ] Fleet commander role

### Enhanced Station Features
- [ ] Station transfer/override mechanics
- [ ] Officer permission levels
- [ ] Station-specific HUD layouts
- [ ] Crew efficiency/fatigue system

### Communication Systems
- [ ] Voice channel integration
- [ ] Text chat per station
- [ ] Ship-to-ship hailing
- [ ] Encrypted communications

### Advanced Gameplay
- [ ] Tutorial/training scenarios for each station
- [ ] Station performance metrics
- [ ] Crew achievements/unlocks
- [ ] Replay/recording system

## Design Decisions

### Why Enum-Based Stations?
- Type-safe station references
- Easy to extend with new stations
- Clear station hierarchy

### Why Separate Manager + Dispatcher?
- **Manager**: State (who controls what)
- **Dispatcher**: Behavior (can they do this?)
- Clean separation of concerns

### Why Filter-on-Read vs Filter-on-Write?
- Simpler implementation
- No need to track what changed
- Stations can be added/removed dynamically

### Why Heartbeat System?
- Detect disconnected clients
- Prevent abandoned station claims
- Clean up stale sessions automatically

## Known Limitations

1. **No station transfer**: Once claimed, must release to switch
2. **No override yet**: Captain can't override other stations' commands
3. **No permission levels**: All crew have same CREW permission
4. **No fleet commands yet**: Single-ship focused
5. **No persistent sessions**: Disconnect = lose claim

## Performance Considerations

- **Client tracking**: O(1) lookup by client_id
- **Station claims**: O(1) lookup by ship_id + station
- **Permission checks**: O(1) set membership test
- **Telemetry filtering**: O(n) field copy (n = number of fields)
- **Cleanup**: Periodic sweep (every tick or on-demand)

## Security Notes

- **No authentication**: Trust all connections (LAN/dev use)
- **No encryption**: Plain JSON over TCP
- **No rate limiting**: Commands processed as received
- **No command validation**: Trust client input (to be added)

For production use, add:
- TLS/SSL for encryption
- Authentication tokens
- Rate limiting per client
- Input validation/sanitization

## Conclusion

Phase 1 of the station-based control architecture is complete and functional. The system provides:

✅ **Multi-crew capability**: Multiple players per ship
✅ **Role-based permissions**: Station-specific command access
✅ **Information filtering**: Appropriate telemetry per station
✅ **Session management**: Robust client tracking and cleanup
✅ **Backward compatibility**: Existing commands still work

The foundation is ready for Phase 2 features including fleet combat, enhanced communications, and advanced crew mechanics.

---

**Implementation by:** Claude (Anthropic)
**Repository:** https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01
**Branch:** claude/station-control-architecture-uIcTD
