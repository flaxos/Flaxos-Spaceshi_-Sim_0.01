# Station-Based Control Architecture

## Overview

The station system enables **multi-crew spaceship control** where different players can control different stations on the same ship, similar to The Expanse TV series. Each station has specific commands and telemetry views appropriate to their role.

## Station Types

| Station | Role | Key Commands | Telemetry |
|---------|------|--------------|-----------|
| **Captain** | Command authority, can override any station | All commands, alert status, override control | Full telemetry |
| **Helm** | Navigation and flight control | Thrust, orientation, autopilot, docking | Position, velocity, fuel, navigation status |
| **Tactical** | Weapons and targeting | Fire weapons, targeting, PDC control | Weapons status, target info, firing solutions |
| **Ops** | Sensors and electronic warfare | Sensor ping, contacts, ECM/ECCM | Sensor contacts, detection log, signature analysis |
| **Engineering** | Power and damage control | Power management, repairs, fuel systems | System status, power grid, damage reports |
| **Comms** | Fleet coordination | Hailing, fleet orders, IFF | Communication log, fleet status, encryption |

## Client Workflow

### 1. Connect to Server

Connect to the TCP server (default port 8765). The server will automatically register your client and send a welcome message with your `client_id`.

```json
{"ok": true, "message": "Connected...", "client_id": "client_1"}
```

### 2. Assign to Ship

Choose which ship you want to join:

```json
{"cmd": "assign_ship", "ship": "test_ship_001"}
```

Response:
```json
{"ok": true, "message": "Assigned to ship test_ship_001"}
```

### 3. Claim a Station

Claim a station on your assigned ship:

```json
{"cmd": "claim_station", "station": "helm"}
```

Response:
```json
{
  "ok": true,
  "message": "Station helm claimed successfully",
  "response": {
    "station": "helm",
    "ship_id": "test_ship_001",
    "available_commands": ["set_thrust", "autopilot", "set_course", ...]
  }
}
```

### 4. Issue Commands

Now you can issue commands appropriate to your station:

```json
{"cmd": "set_thrust", "thrust": 0.5}
```

Notes:
- `set_thrust` is the **primary gameplay** throttle command (scalar `0.0..1.0`) and is applied along the ship’s forward axis, rotated into world-frame by the ship’s quaternion.
- For debug/testing only, the legacy `set_thrust_vector` command accepts `{"x": ..., "y": ..., "z": ...}` (world-frame thrust).

### 5. Get Status

Check your session status:

```json
{"cmd": "my_status"}
```

Check all stations on your ship:

```json
{"cmd": "station_status"}
```

## Station Management Commands

These commands bypass permission checks and are always available:

| Command | Args | Description |
|---------|------|-------------|
| `register_client` | `player_name` | Register client (auto-called on connect) |
| `assign_ship` | `ship` | Assign to a ship |
| `claim_station` | `station` | Claim a station |
| `release_station` | - | Release current station |
| `station_status` | - | Get station status for current ship |
| `my_status` | - | Get current session status |
| `fleet_status` | - | Get status of all ships and crews |
| `heartbeat` | - | Keep session alive |
| `list_ships` | - | List available ships |

## Permission System

The station system enforces command permissions:

1. **Station-specific commands**: Only available if you control the appropriate station
2. **Permission denied**: Attempting unauthorized commands returns an error:
   ```json
   {"ok": false, "message": "Permission denied: Command 'fire_weapon' requires tactical station"}
   ```
3. **Captain override**: Captain station can issue any command

Implementation note:
- Station definitions include some *planned/legacy* command names. The server will return `Unknown command` if a command is allowed by a station definition but not registered with the dispatcher.

## Telemetry Filtering

Each station receives only the telemetry relevant to their role:

- **Helm**: Position, velocity, orientation, fuel, autopilot status
- **Tactical**: Weapons status, target info, firing solutions
- **Ops**: Sensor contacts, detection data
- **Engineering**: System status, power grid, damage reports
- **Captain**: Full telemetry

Use `get_state` to retrieve filtered telemetry:

```json
{"cmd": "get_state", "ship": "test_ship_001"}
```

## Running the Station Server

### Start the server:

```bash
python -m server.station_server --host 0.0.0.0 --port 8765 --dt 0.1 --fleet-dir hybrid_fleet
```

Arguments:
- `--host`: Host to bind to (default: 127.0.0.1)
- `--port`: Port to bind to (default: 8765)
- `--dt`: Simulation timestep in seconds (default: 0.1)
- `--fleet-dir`: Directory containing ship JSON files (default: hybrid_fleet)

## Example Session

```bash
# Terminal 1: Start server
python -m server.station_server

# Terminal 2: Helm station
nc localhost 8765
{"cmd": "assign_ship", "ship": "test_ship_001"}
{"cmd": "claim_station", "station": "helm"}
{"cmd": "set_thrust", "thrust": 0.5}
{"cmd": "autopilot", "program": "hold_velocity"}

# Terminal 3: Tactical station
nc localhost 8765
{"cmd": "assign_ship", "ship": "test_ship_001"}
{"cmd": "claim_station", "station": "tactical"}
{"cmd": "lock_target", "target_id": "C001"}
{"cmd": "fire_weapon", "weapon_type": "torpedo"}
```

## Architecture

### Components

1. **StationType**: Enum defining station types
2. **StationDefinition**: Defines commands and displays for each station
3. **StationManager**: Tracks client sessions and station claims
4. **StationAwareDispatcher**: Routes commands with permission checks
5. **StationTelemetryFilter**: Filters telemetry based on station
6. **StationServer**: Enhanced TCP server with station support

### Data Flow

```
Client → TCP Connection → StationServer
  ↓
  → Client registered with StationManager
  ↓
  → Command received
  ↓
  → StationAwareDispatcher checks permissions
  ↓
  → Command routed to ship system
  ↓
  → Response filtered by StationTelemetryFilter
  ↓
  → Filtered response sent to client
```

## Session Management

- **Auto-registration**: Clients are registered on connection
- **Heartbeat**: Periodic heartbeat keeps session alive (5 min timeout)
- **Auto-cleanup**: Stale sessions are automatically cleaned up
- **Disconnect handling**: Station claims released on disconnect

## Future Enhancements

- **Fleet coordination**: Multi-ship fleet management
- **Permission levels**: Officer/Crew hierarchy
- **Station transfer**: Transfer control between players
- **Override mechanics**: Captain can override station commands
- **Voice channels**: Integration with voice comms
- **Station presets**: Save/load station configurations

## Testing

See `test_station_client.py` for example client code and test scenarios.
