# Flaxos Spaceship Sim - Tutorial Guide

**Version**: 1.0
**Last Updated**: 2026-01-19

Welcome to the Flaxos Spaceship Sim! This tutorial will guide you through the basics of operating a spaceship, working with your crew, and mastering the multi-station interface.

## Table of Contents
- [Getting Started](#getting-started)
- [Understanding Stations](#understanding-stations)
- [Your First Mission](#your-first-mission)
- [Navigation & Flight](#navigation--flight)
- [Sensors & Contacts](#sensors--contacts)
- [Combat Basics](#combat-basics)
- [Multi-Crew Operations](#multi-crew-operations)
- [Advanced Topics](#advanced-topics)

---

## Getting Started

### Prerequisites

**Required:**
- Python 3.8+
- PyYAML (`pip install pyyaml`)
- Flask (`pip install flask`)

**Optional:**
- NumPy (`pip install numpy`) - Required for fleet formations

### Starting the Server

From your project directory:

```bash
# Terminal 1: Start the server
python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --port 8765 --host 0.0.0.0
```

The server will:
1. Load ship configurations from `hybrid_fleet/`
2. Start the physics simulation (0.1s timestep)
3. Listen for client connections on port 8765

### Connecting Your First Client

**Option 1: Desktop HUD (Recommended for Learning)**
```bash
# Terminal 2: Start the HUD
python hybrid/gui/gui.py
```

**Option 2: Mobile UI (Android/Pydroid)**
```bash
# On Android device
python mobile_ui/app.py
# Then open http://<device-ip>:5000 in browser
```

**Option 3: Command-Line Client**
```python
# Terminal 2: Python interactive client
import socket
import json

sock = socket.create_connection(('localhost', 8765))

def cmd(command_dict):
    sock.sendall((json.dumps(command_dict) + "\n").encode())
    return json.loads(sock.recv(4096).decode().strip())

# Now you can issue commands:
cmd({"cmd": "register_client", "player_name": "Alice"})
```

---

## Understanding Stations

The simulator uses a **bridge station system** inspired by submarine and spaceship bridge operations. Each station has specific responsibilities and permissions.

### Station Overview

| Station | Role | Primary Responsibilities |
|---------|------|--------------------------|
| **CAPTAIN** | Commander | Full ship authority, can override any station |
| **HELM** | Pilot | Navigation, thrust, orientation, autopilot |
| **TACTICAL** | Weapons Officer | Weapons, targeting, fire control |
| **OPS** | Operations | Sensors, contacts, ECM, detection |
| **ENGINEERING** | Engineer | Power management, damage control, repairs |
| **COMMS** | Communications | Fleet comms, IFF, hailing |
| **FLEET_COMMANDER** | Admiral | Multi-ship command, formations |

### Permission Levels

1. **CAPTAIN** - Full ship access, sees all events, can override any station
2. **OFFICER** - Station commands + cross-station visibility
3. **CREW** - Station-specific commands only

### Claiming a Station

```python
# Step 1: Register with server
cmd({"cmd": "register_client", "player_name": "Alice"})

# Step 2: Assign to a ship
cmd({"cmd": "assign_ship", "ship": "player_ship"})

# Step 3: Claim a station
result = cmd({"cmd": "claim_station", "station": "helm"})

# Check available commands
print("I can use:", result['data']['available_commands'])
```

**Output:**
```
I can use: ['set_thrust', 'set_orientation', 'autopilot', 'rotate', ...]
```

---

## Your First Mission

Let's complete the **Tutorial: Intercept and Approach** scenario.

### Mission Briefing
- **Objective**: Intercept Tycho Station (54km away) and close to within 1km
- **Difficulty**: Easy
- **Time Limit**: None
- **Ship**: Light Frigate with autopilot

### Step-by-Step Walkthrough

#### 1. Connect and Set Up
```python
# Register and claim HELM station
cmd({"cmd": "register_client", "player_name": "You"})
cmd({"cmd": "assign_ship", "ship": "player_ship"})
cmd({"cmd": "claim_station", "station": "helm"})
```

#### 2. Check Ship Status
```python
state = cmd({"cmd": "get_state", "ship": "player_ship"})
print(f"Position: {state['state']['position']}")
print(f"Velocity: {state['state']['velocity']}")
print(f"Fuel: {state['state']['fuel_mass']} kg")
```

#### 3. Detect the Station (OPS Role)
If you're at HELM, you'll need someone on OPS to handle sensors. For solo play:

```python
# Release HELM temporarily
cmd({"cmd": "release_station"})

# Claim OPS
cmd({"cmd": "claim_station", "station": "ops"})

# Check contacts
events = cmd({"cmd": "get_events", "ship": "player_ship"})
# Look for sensor_contact_detected events

# Optional: Active ping for immediate detection
cmd({"cmd": "ping_sensors", "ship": "player_ship"})
```

The station should appear as contact **C001** or similar.

#### 4. Back to HELM - Engage Intercept
```python
# Release OPS
cmd({"cmd": "release_station"})

# Reclaim HELM
cmd({"cmd": "claim_station", "station": "helm"})

# Engage intercept autopilot
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "intercept",
    "target": "C001"  # Use actual contact ID
})
```

**What happens:**
- Autopilot calculates intercept course
- Ship rotates to face intercept point
- Thrust increases to intercept velocity
- Autopilot transitions through phases:
  1. **INTERCEPT** - Lead pursuit to predicted point
  2. **APPROACH** - Direct pursuit with speed management
  3. **MATCH** - Match velocity for final approach

#### 5. Monitor Progress
```python
# Watch events for autopilot updates
events = cmd({"cmd": "get_events", "ship": "player_ship"})

# Check for autopilot_phase_change events
for event in events['events']:
    if event['type'] == 'autopilot_phase_change':
        print(f"Autopilot: {event['phase']}")
```

#### 6. Final Approach
As you get close (within 5km), autopilot will automatically:
- Reduce thrust to avoid overshoot
- Match velocity with target
- Bring you to a stable position within 1km

#### 7. Mission Complete!
```python
# Check final position
state = cmd({"cmd": "get_state", "ship": "player_ship"})
# Calculate distance to C001...

# Mission accomplished if distance < 1km
```

### Key Lessons Learned
✓ Station claiming and releasing
✓ Using passive sensors to detect contacts
✓ Engaging autopilot intercept mode
✓ Understanding autopilot phases
✓ Monitoring events for updates

---

## Navigation & Flight

### Manual Flight Control

**Setting Thrust:**
```python
# 0.0 = idle, 1.0 = full thrust
cmd({"cmd": "set_thrust", "ship": "player_ship", "thrust": 0.5})
```

**Setting Orientation:**
```python
# Angles in degrees
cmd({
    "cmd": "set_orientation",
    "ship": "player_ship",
    "pitch": 15.0,   # Nose up/down
    "yaw": 45.0,     # Nose left/right
    "roll": 0.0      # Roll around forward axis
})
```

**Applying Angular Velocity:**
```python
# Rates in degrees per second
cmd({
    "cmd": "rotate",
    "ship": "player_ship",
    "pitch_rate": 5.0,
    "yaw_rate": 0.0,
    "roll_rate": 0.0
})
```

### Autopilot Programs

#### Hold Position
Maintain current position (station-keeping).

```python
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "hold"
})
```

**Best for:** Docking, orbiting stations, holding formation

#### Hold Velocity
Maintain current velocity vector (cruise control).

```python
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "hold_velocity"
})
```

**Best for:** Long-distance transit, fuel efficiency

#### Match Velocity
Match velocity with a moving target.

```python
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "match",
    "target": "C001"
})
```

**Best for:** Docking, formation flying, escort missions

#### Intercept
Three-phase intercept of moving target.

```python
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "intercept",
    "target": "C001"
})
```

**Best for:** Combat intercept, rescue operations, urgent rendezvous

**Phases:**
1. **INTERCEPT** - Lead pursuit to predicted intercept point (high speed)
2. **APPROACH** - Direct pursuit with speed management (medium speed)
3. **MATCH** - Velocity matching (low speed)

#### Disable Autopilot
```python
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "off"
})
```

---

## Sensors & Contacts

### Passive Sensors

Passive sensors run continuously in the background, detecting ships based on their **signature**.

**Signature Factors:**
- Thrust level (higher thrust = more visible)
- Ship mass (larger ships more visible)
- Propulsion status (engines on/off)
- Distance (farther = harder to detect)

**Passive Sensor Characteristics:**
- Always active (no power cost)
- ~50-70% accuracy
- Default range: 100km
- Updates every 10 ticks
- Contact classification improves over time

**Checking Contacts:**
```python
events = cmd({"cmd": "get_events", "ship": "player_ship"})

for event in events['events']:
    if event['type'] == 'sensor_contact_detected':
        print(f"New contact: {event['contact_id']}")
        print(f"  Range: {event['range']} m")
        print(f"  Bearing: {event['bearing']}°")
        print(f"  Classification: {event['classification']}")
```

### Active Sensors (Ping)

Active ping provides high-accuracy detection but **reveals your position**.

```python
result = cmd({"cmd": "ping_sensors", "ship": "player_ship"})

# Cooldown: 30 seconds default
print(f"Contacts detected: {result['data']['contacts_detected']}")
print(f"Next ping in: {result['data']['cooldown_remaining']}s")
```

**Active Ping Characteristics:**
- 95%+ accuracy
- Default range: 500km
- Power consumption per ping
- **WARNING: Emits detectable sensor signature!**
- 30-second cooldown

**When to use:**
- Need precise targeting data
- Searching for stealthy contacts
- Emergency navigation
- Not concerned about detection

**When to avoid:**
- Stealth missions
- Enemy sensors nearby
- Passive detection sufficient

### Contact Data

Each contact has:
- **ID**: Stable identifier (C001, C002, ...)
- **Range**: Distance in meters
- **Bearing**: Direction in degrees
- **Closing Speed**: Range rate (negative = approaching)
- **Classification**: Unknown → Small/Medium/Large → Full class
- **Confidence**: Detection accuracy (0.0 to 1.0)
- **Staleness**: Time since last update

---

## Combat Basics

### Weapons Overview

| Weapon | Range | Speed | Guidance | Best Against |
|--------|-------|-------|----------|--------------|
| **Torpedo** | Long (100km+) | Slow | PN Guidance | Large ships, stations |
| **Missile** | Medium (50km) | Fast | Active seeker | Maneuverable targets |
| **PDC** | Short (5km) | Instant | Direct fire | Missiles, torpedoes, close range |

### Engagement Sequence

#### 1. Detect Target (OPS)
```python
# Claim OPS station
cmd({"cmd": "claim_station", "station": "ops"})

# Active ping for accurate targeting
cmd({"cmd": "ping_sensors", "ship": "player_ship"})

# Verify contact
events = cmd({"cmd": "get_events", "ship": "player_ship"})
# Look for sensor_contact_detected
```

#### 2. Intercept (HELM)
```python
# Switch to HELM
cmd({"cmd": "release_station"})
cmd({"cmd": "claim_station", "station": "helm"})

# Engage intercept
cmd({
    "cmd": "autopilot",
    "ship": "player_ship",
    "mode": "intercept",
    "target": "C001"
})
```

#### 3. Fire Weapons (TACTICAL)
```python
# Switch to TACTICAL
cmd({"cmd": "release_station"})
cmd({"cmd": "claim_station", "station": "tactical"})

# Fire torpedo
cmd({
    "cmd": "fire",
    "ship": "player_ship",
    "weapon": "torpedo",
    "target": "C001"
})

# Monitor weapon events
events = cmd({"cmd": "get_events", "ship": "player_ship"})
# Look for weapon_fired, target_locked events
```

#### 4. Evasive Maneuvers (HELM)
If under fire:

```python
cmd({"cmd": "release_station"})
cmd({"cmd": "claim_station", "station": "helm"})

# Emergency thrust
cmd({"cmd": "set_thrust", "ship": "player_ship", "thrust": 1.0})

# Rotate to evade
cmd({
    "cmd": "rotate",
    "ship": "player_ship",
    "pitch_rate": 10.0,
    "yaw_rate": 10.0,
    "roll_rate": 0.0
})
```

### Combat Tips

**Torpedo Tactics:**
- Best at medium-to-long range (20-100km)
- Lead moving targets
- Use multiple torpedoes against agile targets
- Watch fuel - torpedoes have limited range

**PDC Defense:**
- Automatic engagement within arc/range
- Keep pointing toward threats
- Limited ammunition - conserve for critical threats
- Effective against incoming missiles/torpedoes

**ECM/ECCM:**
- ECM reduces enemy missile accuracy
- ECCM improves your missile guidance
- Trade-off: power consumption vs survivability

---

## Multi-Crew Operations

### Two-Person Crew (Minimum)

**Recommended Setup:**
- **Player 1**: CAPTAIN (or HELM + TACTICAL switching)
- **Player 2**: OPS + ENGINEERING switching

**Workflow:**
1. **P2 (OPS)**: Detect contacts, active ping as needed
2. **P1 (HELM)**: Navigate to engagement range
3. **P2 (OPS)**: Maintain contact track, report range/bearing
4. **P1 (TACTICAL)**: Engage targets
5. **P2 (ENGINEERING)**: Monitor systems, manage power

### Three-Person Crew (Optimal)

**Recommended Setup:**
- **Player 1**: CAPTAIN or HELM
- **Player 2**: TACTICAL
- **Player 3**: OPS

**Advantages:**
- No station switching delays
- Simultaneous operations
- Better situational awareness
- Clear division of responsibility

**Communication:**
Use voice chat or text to coordinate:
- "OPS: New contact bearing 045, range 42km"
- "HELM: Intercept course set, ETA 3 minutes"
- "TACTICAL: Torpedo away, time to impact 90 seconds"

### Fleet Operations (4+ Players)

**Setup:**
- **Ship 1**: CAPTAIN, HELM, TACTICAL, OPS
- **Ship 2**: CAPTAIN, HELM, TACTICAL, OPS
- **Fleet Commander**: Separate client issuing fleet commands

**Fleet Commands:**
```python
# Fleet Commander creates fleet
cmd({
    "cmd": "create_fleet",
    "fleet_id": "alpha_squadron",
    "name": "Alpha Squadron",
    "flagship": "ship_1",
    "ships": ["ship_2", "ship_3"]
})

# Set formation
cmd({
    "cmd": "set_fleet_formation",
    "fleet_id": "alpha_squadron",
    "formation": "wedge",
    "spacing": 1000.0
})
```

---

## Advanced Topics

### Fuel Management

**Monitor Fuel:**
```python
state = cmd({"cmd": "get_state", "ship": "player_ship"})
fuel_kg = state['state']['fuel_mass']
fuel_pct = (fuel_kg / ship_max_fuel) * 100
print(f"Fuel: {fuel_pct:.1f}% ({fuel_kg:.0f} kg)")
```

**Fuel Efficiency Tips:**
- Use autopilot for optimal thrust profiles
- Coast when possible (set thrust to 0)
- Avoid high-thrust maneuvers
- Plan delta-v budget before missions

**Emergency Refuel:**
```python
# Engineering station command
cmd({"cmd": "refuel", "ship": "player_ship"})
```

### Power Management

**System Power Control:**
```python
# Power on/off systems (ENGINEERING)
cmd({"cmd": "power_on", "ship": "player_ship", "system": "sensors"})
cmd({"cmd": "power_off", "ship": "player_ship", "system": "propulsion"})
```

**Power Priority:**
1. Life Support (always on)
2. Reactor (power generation)
3. Propulsion (mobility)
4. Sensors (awareness)
5. Weapons (offense)
6. ECM (defense)

**Battery Management:**
- Reactor shutdown → batteries provide backup power
- ~2-4 hours battery life at minimal systems
- Restart reactor before batteries depleted

### Crew Efficiency

**Check Crew Status:**
```python
crew = cmd({"cmd": "my_crew_status"})
print(f"Fatigue: {crew['data']['fatigue']:.1%}")
print(f"Efficiency: {crew['data']['efficiency']:.1%}")
print(f"Success Rate: {crew['data']['success_rate']:.1%}")
```

**Fatigue Effects:**
- 0-25%: Minimal impact
- 25-50%: Slight performance reduction
- 50-75%: Noticeable efficiency loss
- 75-100%: Severe performance degradation

**Rest Breaks:**
```python
# Take a 4-hour rest
cmd({"cmd": "crew_rest", "hours": 4.0})

# Station must be transferred to another crew member during rest
```

### Scenarios & Missions

**Available Scenarios:**
1. **Tutorial: Intercept and Approach** (Easy)
2. **Combat: Eliminate Threat** (Medium)
3. **Escort: Protect the Convoy** (Hard)
4. **Stealth: Silent Observer** (Very Hard)
5. **Race: Belt Runner** (Medium)

See `scenarios/` directory and `README.md` for detailed descriptions.

---

## Troubleshooting

### Common Issues

**"Permission denied" error**
- You're trying to use a command not available to your station
- Claim the correct station or have CAPTAIN override

**"Station required" error**
- You haven't claimed a station yet
- Use `claim_station` command first

**"Not assigned to ship" error**
- You haven't assigned to a ship
- Use `assign_ship` command after registering

**Autopilot not engaging**
- Check that target contact exists
- Verify contact ID is correct (C001, not "station")
- Ensure you're at HELM station

**Sensors not detecting anything**
- Contacts may be out of range (>100km passive)
- Try active ping for long-range detection
- Wait for passive sensor update cycle (~10 ticks)

**Connection timeout**
- Check server is running
- Verify IP address and port (8765)
- Ensure firewall allows TCP connections
- Both devices must be on same network (LAN)

---

## Quick Reference Card

### Essential Commands

| Task | Station | Command |
|------|---------|---------|
| Register | Any | `register_client` |
| Assign ship | Any | `assign_ship` |
| Claim station | Any | `claim_station` |
| Get status | Any | `get_state` |
| Set thrust | HELM | `set_thrust` |
| Autopilot | HELM | `autopilot` |
| Active ping | OPS | `ping_sensors` |
| Fire weapon | TACTICAL | `fire` |
| Check crew | Any | `crew_status` |
| Heartbeat | Any | `heartbeat` |

### Keyboard Shortcuts (GUI only)

- **F**: Fire torpedo
- **P**: Active ping
- **A**: Toggle autopilot
- **R**: Toggle recording
- **ESC**: Emergency stop
- **Tab**: Cycle contacts
- **Space**: Target selected contact

---

## Next Steps

1. **Complete Tutorial Scenario** - Get comfortable with basics
2. **Try Combat Scenario** - Learn weapons and tactics
3. **Multi-Crew Practice** - Coordinate with friends
4. **Advanced Scenarios** - Test your skills in stealth and escort missions
5. **Fleet Operations** - Command multiple ships

For detailed API documentation, see [`docs/API_REFERENCE.md`](API_REFERENCE.md).

For sprint recommendations and development roadmap, see [`docs/SPRINT_RECOMMENDATIONS.md`](SPRINT_RECOMMENDATIONS.md).

---

**Happy flying, Captain!**
