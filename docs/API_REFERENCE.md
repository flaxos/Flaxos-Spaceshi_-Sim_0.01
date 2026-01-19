# TCP JSON API Reference

**Version**: 1.0
**Protocol**: Newline-delimited JSON over TCP
**Last Updated**: 2026-01-19

## Table of Contents
- [Overview](#overview)
- [Connection](#connection)
- [Command Format](#command-format)
- [Station Management](#station-management)
- [Ship Control Commands](#ship-control-commands)
- [Navigation & Autopilot](#navigation--autopilot)
- [Sensors & Targeting](#sensors--targeting)
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

**Response Format:**
```json
{
  "ok": true,
  "message": "Success message",
  "data": { ... }
}
```

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
  "data": {
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
  "data": {
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
  "data": {
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
  "data": {
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
  "data": {
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
  "data": {
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
  "data": {
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
Set propulsion thrust (0.0 to 1.0).

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
  "message": "Thrust set to 50%"
}
```

---

### set_orientation
Set ship orientation (pitch, yaw, roll in degrees).

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
  "message": "Orientation set"
}
```

---

### rotate
Apply angular velocity to ship.

**Station:** HELM
**Request:**
```json
{
  "cmd": "rotate",
  "ship": "player_ship",
  "pitch_rate": 5.0,
  "yaw_rate": 0.0,
  "roll_rate": 0.0
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Angular velocity set"
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
  "mode": "match",
  "target": "C001"
}
```

**Request (Intercept):**
```json
{
  "cmd": "autopilot",
  "ship": "player_ship",
  "mode": "intercept",
  "target": "C001"
}
```

**Request (Hold Position):**
```json
{
  "cmd": "autopilot",
  "ship": "player_ship",
  "mode": "hold"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Autopilot engaged: match velocity",
  "data": {
    "mode": "match",
    "target": "C001"
  }
}
```

---

### set_course
Set navigation waypoint.

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
  "message": "Active ping complete",
  "data": {
    "contacts_detected": 3,
    "cooldown_remaining": 30.0
  }
}
```

---

### get_events
Get filtered events for your station.

**Request:**
```json
{
  "cmd": "get_events",
  "ship": "player_ship"
}
```

**Response:**
```json
{
  "ok": true,
  "events": [
    {
      "type": "sensor_contact_detected",
      "ship_id": "player_ship",
      "contact_id": "C001",
      "timestamp": 123.45
    },
    {
      "type": "autopilot_phase_change",
      "ship_id": "player_ship",
      "phase": "approach",
      "timestamp": 124.0
    }
  ],
  "station": "ops",
  "total_events": 50,
  "filtered_count": 8
}
```

---

## Weapons & Combat

### fire
Fire weapon at locked target.

**Station:** TACTICAL
**Weapon Types:**
- `torpedo` - Guided torpedo
- `pdc` - Point defense cannon
- `missile` - Missile

**Request:**
```json
{
  "cmd": "fire",
  "ship": "player_ship",
  "weapon": "torpedo",
  "target": "C001"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "Torpedo fired at C001",
  "data": {
    "weapon": "torpedo",
    "target": "C001",
    "projectile_id": "proj_001"
  }
}
```

---

### cease_fire
Stop all weapons.

**Station:** TACTICAL
**Request:**
```json
{
  "cmd": "cease_fire",
  "ship": "player_ship"
}
```

**Response:**
```json
{
  "ok": true,
  "message": "All weapons ceased fire"
}
```

---

## Fleet Commands

### create_fleet
Create a new fleet (FLEET_COMMANDER only).

**Station:** FLEET_COMMANDER
**Request:**
```json
{
  "cmd": "create_fleet",
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
  "data": {
    "fleet_id": "alpha_squadron",
    "ship_count": 3
  }
}
```

---

### set_fleet_formation
Set fleet formation.

**Station:** FLEET_COMMANDER
**Formations:** `line`, `wedge`, `column`, `sphere`

**Request:**
```json
{
  "cmd": "set_fleet_formation",
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
  "data": {
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
  "data": {
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
  "data": {
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
  "data": {
    "crew_id": "crew_1",
    "fatigue": 0.12,
    "stress": 0.05
  }
}
```

---

## Event System

### Event Types by Station

Events are filtered based on your station. Some events are visible to all stations.

#### HELM Events
- `autopilot_engaged`
- `autopilot_phase_change`
- `autopilot_complete`
- `navigation_complete`
- `course_set`
- `propulsion_status`
- `docking_initiated`

#### TACTICAL Events
- `weapon_fired`
- `target_locked`
- `target_lost`
- `fire_solution_ready`
- `weapon_reload_complete`
- `pdc_engaged`
- `threat_detected`

#### OPS Events
- `sensor_contact_detected`
- `sensor_contact_lost`
- `sensor_contact_updated`
- `active_ping_complete`
- `detection_warning`
- `ecm_activated`
- `signature_change`

#### ENGINEERING Events
- `power_state_change`
- `reactor_status`
- `damage_report`
- `repair_complete`
- `system_failure`
- `fuel_low`
- `battery_critical`

#### COMMS Events
- `comm_received`
- `fleet_status_update`
- `hail_received`
- `message_sent`
- `iff_change`

#### FLEET_COMMANDER Events
- `fleet_formation_change`
- `fleet_tactical_update`
- `fleet_status_change`
- `engagement_detected`

#### Universal Events (All Stations)
- `critical_alert`
- `mission_update`
- `hint`
- `gimbal_lock_warning`
- `emergency_stop`

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

# Register
response = send_command(sock, {
    "cmd": "register_client",
    "player_name": "Alice"
})
print(f"Registered: {response['data']['client_id']}")

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
print(f"Available commands: {response['data']['available_commands']}")

# Engage autopilot
send_command(sock, {
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "intercept",
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
