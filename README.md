# Flaxos Spaceship Sim — Full Feature Prototype
Hard sci‑fi sim (Expanse‑inspired) with comprehensive navigation, autopilot, sensors, and combat systems. This release includes advanced autonomous navigation, passive/active sensors with contact tracking, targeting systems, and a complete command API.

## Quickstart
```bash
python -m pip install pytest
python -m pytest -q

# Terminal 1: start server
python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --port 8765

# Terminal 2: HUD
python hybrid/gui/gui.py
```

## Android/Pydroid UAT (TCP JSON)
The sim server speaks **newline-delimited JSON over TCP** (one JSON object per line). The Android UI can run in Pydroid and connect over your LAN.

### 1) Install dependencies in Pydroid
```bash
pip install numpy pyyaml flask
```

### 2) Start the server (desktop recommended)
Run the sim server from your desktop/laptop so it can host the simulation loop:
```bash
python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --host 0.0.0.0 --port 8765
```

> If you must run the server on Android, use the same entrypoint/flags in Pydroid; just be mindful of device performance.

### 3) Run the Android UI client (Pydroid)
From the repo root on the Android device:
```bash
python mobile_ui/app.py
```
Then open `http://<android-ip>:5000` in a mobile browser. Use the form to set the sim server host/port.

#### Optional: all-in-one runtime (server + UI in one command)
If you want a single Pydroid command that runs both the sim server and the mobile UI:
```bash
python pydroid_run.py --server-host 127.0.0.1 --server-port 8765 --ui-port 5000
```
Then open `http://<android-ip>:5000` and set the host/port to `127.0.0.1:8765`.

### 4) Port/host + LAN requirements
- **Server host/port:** bind to `0.0.0.0:8765` on the desktop to accept LAN traffic.
- **Client host/port:** in the UI, set host to the desktop's LAN IP (e.g. `192.168.1.20`) and port `8765`.
- **Network:** both devices must be on the same Wi‑Fi/LAN and firewall must allow TCP 8765.

### Smoke test (connectivity)
Run from any machine on the LAN (including Pydroid) to verify the TCP JSON protocol:
```bash
python - <<'PY'
import json, socket
host = "192.168.1.20"  # replace with your server IP
port = 8765
with socket.create_connection((host, port), timeout=3) as sock:
    sock.sendall((json.dumps({"cmd": "get_state"}) + "\n").encode())
    print(sock.recv(4096).decode().strip())
PY
```

## Demo
- **Interceptor** (torp launcher) vs **Target** (PDC + ECM=0.4, evasive AI).
- In HUD: click `Target` to lock, press **F** to fire, **P** to ping, **A** toggle autopilot, **R** record.

## New Features (Full Prototype Release)

### 🎯 Advanced Sensor System
- **Passive Sensors**: Continuous background scanning with probabilistic detection
  - Range-based accuracy degradation
  - Signature calculation from thrust, mass, propulsion status
  - Contact classification (Unknown → Small/Medium/Large → Full class)
  - Configurable update intervals (default: every 10 ticks)

- **Active Sensors**: High-accuracy manual ping system
  - 95%+ accuracy vs passive's ~50-70%
  - Longer range (500km vs 100km default)
  - Cooldown mechanism (30s default)
  - Power consumption per ping
  - **Warning**: Active pings emit detectable sensor signature!

- **Contact Management**
  - Stable contact IDs (C001, C002, ...) mapped from real ship IDs
  - Contact aging and staleness tracking
  - Automatic confidence decay over time
  - Contact pruning after extended staleness
  - Distance-sorted contact lists with bearing/range/closing speed

### 🚀 Autonomous Navigation & Autopilot
- **Navigation Controller**: Mode arbitration system
  - Manual, autopilot, and manual_override modes
  - Manual override with timeout (returns to autopilot after 5s)
  - Real-time mode switching without interruption

- **Autopilot Programs**:
  - **Match Velocity**: PID controller to null relative velocity with target
    - Smooth exponential approach curve
    - Deceleration planning to prevent overshoot
    - Configurable tolerance (default: 1.0 m/s)

  - **Intercept**: Three-phase intercept using lead pursuit
    - Phase 1 (Intercept): Lead pursuit to predicted intercept point
    - Phase 2 (Approach): Direct pursuit with speed management
    - Phase 3 (Match): Delegates to match velocity for final approach
    - Automatic phase transitions based on range/closing speed

  - **Hold Position**: Station-keeping with drift correction
  - **Hold Velocity**: Cruise control maintaining current velocity

- **Relative Motion Calculations**:
  - Range, range rate (closing speed), lateral velocity
  - Time to closest approach (TCA) and CPA distance
  - Bearing and aspect angle calculations
  - Collision course detection
  - Intercept time/point prediction

### 🎯 Targeting System
- Target lock/unlock with firing state protection
- Lock quality tracking from sensor confidence
- Automatic lock degradation when contact is lost
- Firing solution calculation (range, bearing, TCA, CPA)
- Integration with sensors and weapons

### 🛡️ Safety & Robustness
- **NaN/Inf Guards**: Comprehensive validation in physics update loop
- **State Sanitization**: Automatic recovery from invalid physics states
- **Input Validation**: Type-safe command argument validation
  - Float, int, str, bool, angle, vector3 types
  - Range checking and normalization
  - Clear error messages with suggestions

### 📊 Telemetry & Utilities
- **Unified Telemetry System**: Consistent state export for all consumers
- **Units Module**: Auto-scaling formatters (m/km, deg/rad, kg/tonnes)
- **Delta-v Calculation**: Tsiolkovsky rocket equation for fuel planning
- **Error Handling**: Structured error types with actionable messages

## Demo Commands to Try

### Basic Flight
```bash
status              # Show comprehensive ship status
thrust 0.5          # Set thrust to 50%
heading 45 0        # Set heading (pitch, yaw)
position            # Get current position
velocity            # Get current velocity
```

### Sensors & Targeting
```bash
contacts            # List all sensor contacts
ping                # Active sensor ping (high accuracy, reveals position!)
target C001         # Lock target C001
untarget            # Unlock current target
```

### Autopilot
```bash
# Match velocity with a target
autopilot match C001

# Intercept a moving target
autopilot intercept C001

# Hold current position (station-keeping)
autopilot hold

# Hold current velocity (cruise control)
autopilot hold_velocity

# Disengage autopilot
autopilot off
```

### Combat
```bash
target C001         # Lock target
fire torpedo        # Fire torpedo at locked target
fire pdc            # Enable point defense
cease_fire          # Stop all weapons
```

### System Control
```bash
power_on sensors    # Power on a system
power_off propulsion # Power off a system
refuel              # Refuel to maximum
emergency_stop      # Emergency stop all thrust
```

## What's in Sprint 2 (Previous Release)
- **Missiles/Torps/Nukes**: PN-like guidance; seeker FOV; ECM/ECCM (wider FOV + turn authority); proximity fusing; nuke AoE.
- **Point Defense**: Automatic engagement inside arc/range/FOV.
- **Server API**: `get_state`, `get_events`, `get_mission`, `fire_weapon`, `set_target`, `ping_sensors`, recording controls.
