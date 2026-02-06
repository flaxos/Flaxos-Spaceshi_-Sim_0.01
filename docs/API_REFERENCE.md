# TCP JSON API Reference

**Protocol Version**: 1.0
**Wire Format**: Newline-delimited JSON over TCP (NDJSON)
**Last Updated**: 2026-01-26

## Table of Contents
- [Overview](#overview)
- [Server Entrypoint](#server-entrypoint)
- [Connection](#connection)
- [Command Format](#command-format)
- [Autodiscovery](#autodiscovery)
- [Station Management](#station-management)
- [Ship Control Commands](#ship-control-commands)
- [Navigation & Autopilot](#navigation--autopilot)
- [Sensors & Targeting](#sensors--targeting)
- [Engineering & Power Management](#engineering--power-management)
- [Weapons & Combat](#weapons--combat)
- [Fleet Commands](#fleet-commands)
- [Crew Management](#crew-management)
- [Event System](#event-system)
- [Error Handling](#error-handling)

---

## Overview

The Flaxos Spaceship Sim server communicates via **TCP JSON protocol**. Commands are sent as JSON objects terminated by a newline character (`\n`). Each command receives a JSON response.

### Protocol Requirements
- One JSON object per line
- Commands must include a `"cmd"` field
- Most commands require a `"ship"` field (auto-filled if assigned)
- All JSON strings must be properly escaped
- Optional `_request_id` field for request/response correlation

---

## Server Entrypoint

Use the unified server entrypoint:

```bash
# Station mode (multi-crew, default)
python -m server.main

# Minimal mode (no station management)
python -m server.main --mode minimal

# LAN accessible
python -m server.main --lan

# Custom port
python -m server.main --port 9000
```

### Default Ports
| Service | Port | Description |
|---------|------|-------------|
| TCP Server | 8765 | Main simulation server |
| WebSocket Bridge | 8080 | Browser client bridge |
| HTTP GUI | 3000 | Static file server |

### Full GUI Stack
```bash
# Start everything (server + WS bridge + HTTP server)
python tools/start_gui_stack.py

# With options
python tools/start_gui_stack.py --mode station --lan
```

---

## Connection

### Connect to Server
```python
import socket
import json

# Connect
sock = socket.create_connection(('192.168.1.20', 8765), timeout=5)

# Send command
command = {"cmd": "register_client", "player_name": "Alice"}
sock.sendall((json.dumps(command) + "\n").encode())

# Receive response
response = json.loads(sock.recv(4096).decode().strip())
```

### Connection Flow
1. **Connect** to server TCP socket
2. **Register** client with `register_client`
3. **Assign** to ship with `assign_ship`
4. **Claim** station with `claim_station`
5. **Issue** commands based on station permissions

---

## Autodiscovery

Clients can query server configuration using the `_discover` command:

**Request:**
```json
{
  "cmd": "_discover"
}
```

**Response:**
```json
{
  "ok": true,
  "version": "1.0",
  "mode": "station",
  "endpoints": {
    "tcp": {"host": "127.0.0.1", "port": 8765},
    "ws": {"host": "127.0.0.1", "port": 8080},
    "http": {"host": "127.0.0.1", "port": 3000}
  },
  "features": {
    "stations": true,
    "multi_crew": true,
    "fleet_commands": true
  }
}
```

This allows GUI clients to auto-configure connection settings.

---

## Command Format

All commands follow this structure:

```json
{
  "cmd": "command_name",
  "ship": "ship_id",
  "arg1": "value1",
  "arg2": "value2"
}
```

**Response Format (station server commands):**
```json
{
  "ok": true,
  "message": "Success message",
  "response": { ... }
}
```

Notes:
- Some “direct” server handlers (notably `get_state`, `get_events`, `list_scenarios`, `load_scenario`, `get_mission`, `get_mission_hints`) may return a command-specific payload without a `message/response` wrapper.
- The **basic server** (`server.run_server`) uses a different response shape for some commands (see `server/run_server.py`).

**Error Response:**
```json
{
  "ok": false,
  "error": "Error description",
  "code": "ERROR_CODE"
}
```

---

## Station Management

### register_client
Register a new client with the server.

> In `server.station_server`, clients are auto-registered on connect and receive a welcome message containing `client_id`. Calling `register_client` is optional (use it to set a display name).

**Request:**
```json
{
  "cmd": "register_client",
  "player_name": "Alice"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Client registered as Alice",
  "response": {
    "client_id": "client_1",
    "player_name": "Alice",
    "session": {
      "client_id": "client_1",
      "player_name": "Alice",
      "ship_id": null,
      "station": null
    }
  }
}
```

---

### assign_ship
Assign client to a ship.

**Request:**
```json
{
  "cmd": "assign_ship",
  "ship": "player_ship"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Assigned to ship player_ship",
  "response": {
    "ship_id": "player_ship"
  }
}
```

---

### claim_station
Claim a station on your assigned ship.

**Station Types:**
- `captain` - Full ship control
- `helm` - Navigation, thrust, orientation
- `tactical` - Weapons, targeting
- `ops` - Sensors, contacts
- `engineering` - Power, damage control
- `comms` - Communications, IFF
- `fleet_commander` - Fleet management

**Request:**
```json
{
  "cmd": "claim_station",
  "station": "helm"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Claimed helm station",
  "response": {
    "station": "helm",
    "ship_id": "player_ship",
    "available_commands": [
      "set_thrust",
      "set_orientation",
      "set_angular_velocity",
      "rotate",
      "autopilot",
      "helm_override"
    ]
  }
}
```
> `available_commands` only includes commands that are registered with the station dispatcher. Planned or legacy-only commands are intentionally omitted.

---

### release_station
Release your current station.

**Request:**
```json
{
  "cmd": "release_station"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Released helm station"
}
```

---

### my_status
Get your current session status.

**Request:**
```json
{
  "cmd": "my_status"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Session status",
  "response": {
    "client_id": "client_1",
    "player_name": "Alice",
    "ship_id": "player_ship",
    "station": "helm",
    "permission_level": "CREW",
    "available_commands": ["set_thrust", "autopilot", ...]
  }
}
```

---

### station_status
Get status of all stations on your ship.

**Request:**
```json
{
  "cmd": "station_status"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Station status",
  "response": {
    "ship_id": "player_ship",
    "stations": [
      {"station": "captain", "claimed": true, "player": "Bob"},
      {"station": "helm", "claimed": true, "player": "Alice"},
      {"station": "tactical", "claimed": false, "player": null}
    ]
  }
}
```

---

### list_ships
List all available ships in the simulation.

**Request:**
```json
{
  "cmd": "list_ships"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Ships list",
  "response": {
    "ships": [
      {"id": "test_ship_001", "name": "Test Ship 001"},
      {"id": "freighter_alpha", "name": "Freighter Alpha"}
    ]
  }
}
```

---

### fleet_status
Get status of all ships and their crews.

**Request:**
```json
{
  "cmd": "fleet_status"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Fleet status",
  "response": {
    "ships": {
      "player_ship": [
        {"station": "captain", "player": "Bob"},
        {"station": "helm", "player": "Alice"}
      ]
    },
    "clients": [
      {
        "client_id": "client_1",
        "player_name": "Alice",
        "ship_id": "player_ship",
        "station": "helm"
      }
    ]
  }
}
```

---

### heartbeat
Keep session alive (prevents timeout).

**Request:**
```json
{
  "cmd": "heartbeat"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Heartbeat received",
  "response": {
    "client_id": "client_1",
    "last_heartbeat": "2026-01-19T21:00:00"
  }
}
```

---

## Ship Control Commands

### get_state
Get ship telemetry (filtered by station).

**Request:**
```json
{
  "cmd": "get_state",
  "ship": "player_ship"
}
```

**Response:**
```json
{
  "ok": true,
  "t": 123.45,
  "ship": "player_ship",
  "state": {
    "position": {"x": 1000.0, "y": 2000.0, "z": 3000.0},
    "velocity": {"x": 10.0, "y": 0.0, "z": 0.0},
    "orientation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
    "thrust": 0.5,
    "fuel_mass": 5000.0,
    "systems": { ... }
  }
}
```

---

### set_thrust
Set main drive throttle (0.0 to 1.0).

**Expanse-style physics:** Thrust is applied along the ship's forward axis (+X in ship frame), then rotated to world frame by the ship's quaternion attitude. This means the ship must be pointed in the direction you want to accelerate.

**Station:** HELM
**Request:**
```json
{
  "cmd": "set_thrust",
  "ship": "player_ship",
  "thrust": 0.5
}
```

**Response:**
```json
{
  "ok": true,
  "throttle": 0.5,
  "thrust_magnitude": 50.0
}
```

---

### set_thrust_vector (DEBUG)
Set arbitrary thrust vector in world frame. **Debug/development only** - bypasses realistic ship-frame physics.

**Station:** HELM
**Request:**
```json
{
  "cmd": "set_thrust_vector",
  "ship": "player_ship",
  "x": 50.0,
  "y": 0.0,
  "z": 0.0
}
```

**Response:**
```json
{
  "ok": true,
  "debug_mode": true,
  "thrust_vector": {"x": 50.0, "y": 0.0, "z": 0.0}
}
```

---

### set_orientation
Set attitude target for RCS. The ship will rotate to achieve this orientation using torque from RCS thrusters - **not instantaneous**.

**Expanse-style physics:** Orientation changes take time as RCS thrusters fire to produce torque. For flip-and-burn maneuvers, set the target heading and wait for the ship to rotate before applying main drive thrust.

**Station:** HELM
**Request:**
```json
{
  "cmd": "set_orientation",
  "ship": "player_ship",
  "pitch": 15.0,
  "yaw": 45.0,
  "roll": 0.0
}
```

**Response:**
```json
{
  "ok": true,
  "status": "Attitude target set (RCS will maneuver)",
  "target": {"pitch": 15.0, "yaw": 45.0, "roll": 0.0}
}
```

---

### rotate
Apply rotation command (adds to current attitude target).

**Station:** HELM
**Request:**
```json
{
  "cmd": "rotate",
  "ship": "player_ship",
  "axis": "yaw",
  "amount": 90.0
}
```

**Response:**
```json
{
  "ok": true,
  "status": "Rotate 90° on yaw commanded",
  "target": {"pitch": 0.0, "yaw": 90.0, "roll": 0.0}
}
```

---

## Navigation & Autopilot

### autopilot
Engage autopilot with a specific program.

**Station:** HELM
**Programs:**
- `off` - Disable autopilot
- `hold` - Hold current position
- `hold_velocity` - Maintain current velocity
- `match` - Match velocity with target
- `intercept` - Intercept moving target

**Request (Match Velocity):**
```json
{
  "cmd": "autopilot",
  "ship": "player_ship",
  "program": "match",
  "target": "C001"
}
```

**Request (Intercept):**
```json
{
  "cmd": "autopilot",
  "ship": "player_ship",
  "program": "intercept",
  "target": "C001"
}
```

**Request (Hold Position):**
```json
{
  "cmd": "autopilot",
  "ship": "player_ship",
  "program": "hold"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Autopilot engaged: match velocity",
  "response": {
    "ok": true,
    "status": "Autopilot engaged: match velocity",
    "program": "match",
    "target": "C001"
  }
}
```

---

### set_course
Set navigation waypoint.

> Note: `set_course` is currently not implemented in the navigation system and will return a NOT_IMPLEMENTED error in most builds.

**Station:** HELM
**Request:**
```json
{
  "cmd": "set_course",
  "ship": "player_ship",
  "x": 50000.0,
  "y": 10000.0,
  "z": 0.0
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Course set"
}
```

---

## Sensors & Targeting

### ping_sensors
Active sensor ping (high accuracy, reveals position).

**Station:** OPS
**Request:**
```json
{
  "cmd": "ping_sensors",
  "ship": "player_ship"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Ping complete: 3 contacts detected",
  "response": {
    "ok": true,
    "status": "Ping complete: 3 contacts detected",
    "contacts_detected": 3,
    "cooldown": 30.0
  }
}
```

---

### get_events
Get filtered events for your station.

Events are pulled from the simulator event log and filtered by station role and assigned ship. In station mode, you must **claim a station** first; otherwise the response is empty with a helpful message. In minimal mode, `get_events` returns the unfiltered event list.

**Request:**
```json
{
  "cmd": "get_events",
  "limit": 100
}
```

**Response:**
```json
{
  "ok": true,
  "events": [
    {
      "type": "autopilot_phase_change",
      "ship_id": "player_ship",
      "message": "Autopilot phase: APPROACH",
      "t": 123.4
    }
  ],
  "station": "ops",
  "total_events": 42,
  "filtered_count": 1
}
```

---

## Engineering & Power Management

### Command Contract (Power Commands)
All power-control commands are routed through the same `PowerManagementSystem.command()` entrypoint in ship command handling. GUI and CLI clients should use identical payloads.

| Command | Required fields | Notes |
|---|---|---|
| `set_power_profile` | `profile` | Applies configured engineering profile data. |
| `set_power_allocation` | `allocation` (object of bus->ratio) | Bus keys remain data-driven from ship/schema config. |
| `get_power_profiles` | none | Returns `profiles`, `active_profile`, and profile `definitions`. |
| `get_power_telemetry` | none | Returns allocation/supply/draw snapshots in kW. |
| `get_draw_profile` | none | Returns enabled-system draw grouped by configured bus mapping. |
| `toggle_system_power` | `system`, `enabled` | Toggles any system with an `enabled` flag via power command routing. |

---

### set_power_allocation
Set bus allocation ratios for the active ship power-management system.

**Station:** ENGINEERING

**Request:**
```json
{
  "cmd": "set_power_allocation",
  "ship": "player_ship",
  "allocation": {
    "primary": 0.5,
    "secondary": 0.3,
    "tertiary": 0.2
  }
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Power allocation updated",
  "response": {
    "status": "power_allocation_updated",
    "power_allocation": {
      "primary": 0.5,
      "secondary": 0.3,
      "tertiary": 0.2
    }
  }
}
```

---

### set_power_profile
Apply a predefined engineering power profile (offensive/defensive) to update power allocation, overdrive limits, and weapon/system enablement.

**Station:** ENGINEERING

**Request:**
```json
{
  "cmd": "set_power_profile",
  "ship": "player_ship",
  "profile": "offensive"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Power profile 'offensive' applied",
  "response": {
    "status": "power_profile_applied",
    "profile": "offensive",
    "power_allocation": {
      "primary": 0.6,
      "secondary": 0.25,
      "tertiary": 0.15
    },
    "overdrive_limits": {
      "primary": 1.2,
      "secondary": 1.0,
      "tertiary": 1.0
    }
  }
}
```

---

### get_power_profiles
List available engineering profiles and the current active profile.

**Station:** ENGINEERING

**Request:**
```json
{
  "cmd": "get_power_profiles",
  "ship": "player_ship"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Power profiles retrieved",
  "response": {
    "profiles": ["defensive", "offensive"],
    "active_profile": "offensive",
    "definitions": {
      "offensive": {
        "power_allocation": {
          "primary": 0.6,
          "secondary": 0.25,
          "tertiary": 0.15
        },
        "overdrive_limits": {
          "primary": 1.2,
          "secondary": 1.0,
          "tertiary": 1.0
        },
        "systems": {
          "railgun": {"enabled": true, "power_draw": 60.0},
          "pdc": {"enabled": true, "power_draw": 18.0},
          "ecm": {"enabled": false, "power_draw": 0.0},
          "eccm": {"enabled": false, "power_draw": 0.0}
        }
      }
    }
  }
}
```

---


### get_power_telemetry
Return current power telemetry in physical units (kW), including allocation, available supply per bus, and draw per bus.

**Station:** ENGINEERING

**Request:**
```json
{
  "cmd": "get_power_telemetry",
  "ship": "player_ship"
}
```

**Response (shape):**
```json
{
  "ok": true,
  "response": {
    "allocation": {"primary": 0.5, "secondary": 0.3, "tertiary": 0.2},
    "reactors": {"primary": {"capacity": 1000.0, "available": 800.0}},
    "total_capacity_kw": 1750.0,
    "total_available_kw": 1300.0,
    "supply_by_bus_kw": {"primary": 650.0, "secondary": 390.0, "tertiary": 260.0},
    "draw_by_bus_kw": {"primary": 120.0, "secondary": 45.0, "tertiary": 30.0},
    "active_profile": "offensive"
  }
}
```

---

### get_draw_profile
Return enabled-system draw grouped by bus mapping (`system_map`) from ship config/schema.

**Station:** ENGINEERING

**Request:**
```json
{
  "cmd": "get_draw_profile",
  "ship": "player_ship"
}
```

**Response (shape):**
```json
{
  "ok": true,
  "response": {
    "draw_by_bus": {
      "primary": {
        "draw_kw": 120.0,
        "systems": {
          "propulsion": 80.0,
          "railgun": 40.0
        }
      }
    },
    "total_draw_kw": 165.0
  }
}
```

---
## Weapons & Combat

### fire_weapon
Fire a weapon. If `target` is omitted, the server will attempt to use the currently locked target (if available).

**Station:** TACTICAL
**Weapons:** Depends on ship loadout (commonly `torpedo`, `pdc`, `missile`).

**Request:**
```json
{
  "cmd": "fire_weapon",
  "ship": "player_ship",
  "weapon": "torpedo",
  "target": "C001"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Weapon 'torpedo' fired",
  "response": {
    "ok": true,
    "weapon": "torpedo",
    "target": "C001",
    "damage": 10.0
  }
}
```

---

### cease_fire (not implemented)
Some older docs/clients reference `cease_fire`, but it is not currently registered as a station-server command. Prefer weapon-specific control via `fire_weapon` (and any weapon-system specific flags if/when added).

---

## Fleet Commands

### fleet_create
Create a new fleet (FLEET_COMMANDER only).

**Station:** FLEET_COMMANDER
**Request:**
```json
{
  "cmd": "fleet_create",
  "fleet_id": "alpha_squadron",
  "name": "Alpha Squadron",
  "flagship": "player_ship",
  "ships": ["escort_1", "escort_2"]
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Fleet 'Alpha Squadron' created",
  "response": {
    "fleet_id": "alpha_squadron",
    "name": "Alpha Squadron",
    "flagship": "player_ship",
    "ships": ["escort_1", "escort_2"]
  }
}
```

---

### fleet_form
Form fleet into a formation.

**Station:** FLEET_COMMANDER
**Formations:** `line`, `wedge`, `column`, `sphere`, `wall`, `echelon`, `diamond`

**Request:**
```json
{
  "cmd": "fleet_form",
  "fleet_id": "alpha_squadron",
  "formation": "wedge",
  "spacing": 1000.0
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Formation set to wedge",
  "response": {
    "fleet_id": "alpha_squadron",
    "formation": "wedge",
    "spacing": 1000.0
  }
}
```

---

## Crew Management

### crew_status
Get crew roster for your ship.

**Request:**
```json
{
  "cmd": "crew_status"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Crew status for player_ship",
  "response": {
    "ship_id": "player_ship",
    "crew_count": 3,
    "crew": [
      {
        "crew_id": "crew_1",
        "name": "Alice Chen",
        "skills": {
          "PILOTING": 4,
          "GUNNERY": 3
        },
        "fatigue": 0.25,
        "efficiency": 0.85
      }
    ]
  }
}
```

---

### my_crew_status
Get your personal crew member status.

**Request:**
```json
{
  "cmd": "my_crew_status"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Status for Alice Chen",
  "response": {
    "crew_id": "crew_1",
    "name": "Alice Chen",
    "skills": {"PILOTING": 4, "GUNNERY": 3},
    "fatigue": 0.25,
    "stress": 0.1,
    "efficiency": 0.85,
    "commands_executed": 150,
    "success_rate": 0.94
  }
}
```

---

### crew_rest
Take a rest period (reduces fatigue).

**Request:**
```json
{
  "cmd": "crew_rest",
  "hours": 4.0
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Alice Chen rested for 4.0 hours",
  "response": {
    "crew_id": "crew_1",
    "fatigue": 0.12,
    "stress": 0.05
  }
}
```

---

## Event System

The simulator publishes events to an in-process event bus and maintains a recent event log. TCP servers expose this log via `get_events`, with **station-based filtering** so clients only see relevant events for their role and assigned ship.

### Event Types by Station

Events are filtered based on your station and assigned ship. Filtering is performed by matching event type keywords (e.g., `autopilot`, `weapon`, `sensor`, `power`). Some events are visible to all stations.

#### HELM Events
- Types containing: `autopilot`, `navigation`, `propulsion`

#### TACTICAL Events
- Types containing: `weapon`, `target`

#### OPS Events
- Types containing: `sensor`, `contact`

#### ENGINEERING Events
- Types containing: `power`, `reactor`, `damage`

#### COMMS Events
- Types containing: `comm`

#### FLEET_COMMANDER Events
- Types containing: `fleet`

#### Universal Events (All Stations)
- Types containing: `critical`, `alert`, `warning`, `mission`

---

## Error Handling

### Common Error Codes

| Code | Description |
|------|-------------|
| `MISSING_CMD` | No command specified |
| `MISSING_SHIP` | Ship ID required but not provided |
| `PERMISSION_DENIED` | Station lacks permission for command |
| `STATION_REQUIRED` | Must claim a station first |
| `SHIP_NOT_FOUND` | Ship ID not found in simulation |
| `INVALID_ARGUMENT` | Command argument invalid or out of range |
| `SYSTEM_NOT_FOUND` | Ship system not available |
| `TARGET_NOT_FOUND` | Target contact not found |
| `COOLDOWN_ACTIVE` | Command on cooldown |

### Error Response Example

```json
{
  "ok": false,
  "error": "Permission denied: CREW at HELM cannot issue TACTICAL commands",
  "code": "PERMISSION_DENIED",
  "required_station": "tactical",
  "current_station": "helm"
}
```

---

## Best Practices

1. **Always register** before issuing commands
2. **Claim appropriate station** for the commands you need
3. **Handle errors gracefully** - check `ok` field in responses
4. **Use heartbeat** to keep session alive (every 30-60s)
5. **Filter events** by subscribing only to relevant event types
6. **Respect cooldowns** on active sensors and weapons
7. **Check permissions** before attempting restricted commands

---

## Examples

### Complete Multi-Crew Session

```python
import socket
import json

def send_command(sock, cmd):
    """Send command and get response"""
    sock.sendall((json.dumps(cmd) + "\n").encode())
    return json.loads(sock.recv(4096).decode().strip())

# Connect
sock = socket.create_connection(('192.168.1.20', 8765))

# station_server sends a welcome message immediately on connect:
welcome = json.loads(sock.recv(4096).decode().strip())
print(f"WELCOME: {welcome}")

# Optional: set a display name
response = send_command(sock, {"cmd": "register_client", "player_name": "Alice"})
print(f"Registered: {response['response']['client_id']}")

# Assign to ship
send_command(sock, {
    "cmd": "assign_ship",
    "ship": "player_ship"
})

# Claim helm station
response = send_command(sock, {
    "cmd": "claim_station",
    "station": "helm"
})
print(f"Available commands: {response['response']['available_commands']}")

# Engage autopilot
send_command(sock, {
    "cmd": "autopilot",
    "ship": "player_ship",
    "program": "intercept",
    "target": "C001"
})

# Get ship state
state = send_command(sock, {
    "cmd": "get_state",
    "ship": "player_ship"
})
print(f"Position: {state['state']['position']}")

# Release station when done
send_command(sock, {"cmd": "release_station"})

sock.close()
```

---

**End of API Reference**
