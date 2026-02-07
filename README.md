# Flaxos Spaceship Sim — Full Feature Prototype
Hard sci‑fi sim (Expanse‑inspired) with comprehensive navigation, autopilot, sensors, combat systems, and **station-based multi-crew** control. This release includes advanced autonomous navigation, passive/active sensors with contact tracking, targeting systems, realistic **power management in kW**, and a complete command API.

## Station Architecture & Multi-Crew
The sim supports multiple clients on the same ship with **station roles** (Captain, Helm, Tactical, Ops, Engineering, Comms, Fleet Commander). Each station gets filtered telemetry, role-appropriate commands, and event feeds so multi-crew teams can coordinate in real time.

- **Station server entrypoint:** `python -m server.station_server` (station-aware multi-crew)
- **Unified server entrypoint:** `python -m server.main` (defaults to station mode)
- **Minimal mode:** `python -m server.main --mode minimal` (no station filtering)

## Power Management Highlights
- Reactor warm-up and ramp output in kW
- Primary/Secondary/Tertiary power buses with allocation ratios
- Battery-backed secondary bus and system toggles
- Engineering station command set for routing and monitoring

## Quickstart
```bash
python -m pip install pytest
python -m pytest -q

# Terminal 1: start server (recommended: station-aware / multi-crew)
python -m server.station_server --fleet-dir hybrid_fleet --dt 0.1 --port 8765

# Minimal server (no stations / simplest behavior)
# python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --port 8765

# Terminal 2: GUI client (Tkinter)
python hybrid/gui/run_gui.py --config ships_config.json
```

## Web GUI Quickstart
```bash
python tools/start_gui_stack.py --server station
```
This starts the TCP sim server, WebSocket bridge, and GUI HTTP server, then opens the GUI.

## Documentation
- [Architecture overview](docs/ARCHITECTURE.md)
- [Station architecture](STATION_ARCHITECTURE.md)
- [API reference](docs/API_REFERENCE.md)
- [Gate Horizons integration](docs/INTEGRATION_GATE_HORIZONS.md)
- [Drift guardrails](docs/DRIFT_GUARDRAILS.md)
- [AI agent rules](docs/AI_AGENT_RULES.md)
- [Getting started tutorial](docs/TUTORIAL.md)
- [Feature status](docs/FEATURE_STATUS.md)
- [Known issues](docs/KNOWN_ISSUES.md)
- [Sprint plan](docs/NEXT_SPRINT.md)
- [Next release plan](docs/NEXT_RELEASE_PLAN.md)
- [Quaternion API](docs/QUATERNION_API.md)
- [RCS configuration guide](docs/RCS_CONFIGURATION_GUIDE.md)
- [Physics update notes](docs/PHYSICS_UPDATE.md)

## Role in the Gate Horizons universe
Flaxos Spaceship Sim is the real-time, physics-first tactical mission runtime for ship encounters in the Gate Horizons universe. It simulates RCS attitude control and Epstein main-drive thrust, runs the encounter at real-time cadence, and reports outcomes via a strict contract so the strategic layer can move on. It is not the strategic layer itself, and it does not own campaign logic or canon. The contract name and JSON artefacts are fixed now to prevent drift.

- This repo is the **real-time tactical mission engine** (RCS + Epstein drive).
- Gate Horizons is the **strategic meta layer** (months-scale travel via gates/wormholes, lore, canon, encounter generation).
- Integration is **contract-only**: `EncounterSpec.json` in, `ResultSpec.json` out (conceptual only; do not implement).

### Canon & Style References (Gate Horizons)
- [Gate Horizons canon pack (repo root)](https://github.com/Flaxos/gate-horizons-canon-pack)
- [canon/CANON.md](https://github.com/Flaxos/gate-horizons-canon-pack/blob/main/canon/CANON.md)
- [canon/STYLE_BIBLE.md](https://github.com/Flaxos/gate-horizons-canon-pack/blob/main/canon/STYLE_BIBLE.md)
- [canon/STORYBOARD.md](https://github.com/Flaxos/gate-horizons-canon-pack/blob/main/canon/STORYBOARD.md)
- [canon/IMAGE_PROMPT_TEMPLATE.md](https://github.com/Flaxos/gate-horizons-canon-pack/blob/main/canon/IMAGE_PROMPT_TEMPLATE.md)
- [canon/AI_AGENT_RULES.md](https://github.com/Flaxos/gate-horizons-canon-pack/blob/main/canon/AI_AGENT_RULES.md)

### Operating modes
**Standalone sandbox/multi-station game**
- Run scenarios, skirmishes, and training missions locally.
- Multi-crew stations and AI can be used for co-op or solo play.

**Encounter Runner (Gate Horizons contract runtime)**
- Loads an encounter definition (`EncounterSpec.json`) to spawn actors, initial states, objectives, and rules.
- Runs the mission in real time with the existing physics model.
- Emits a mission result (`ResultSpec.json`) that the meta game can consume.

### Contract-only integration boundary
This repo integrates with Gate Horizons via contract-only artefacts:
- **Input:** `EncounterSpec.json` (spawn list, initial state, objectives, rules, scenario metadata)
- **Output:** `ResultSpec.json` (outcomes, resource usage, losses, mission flags, timelines)

No direct coupling to Gate Horizons internal state or data models is permitted. If a detail is not in the encounter contract, it does not belong inside this runtime.

### Timescale alignment
Gate Horizons operates at a strategic timescale (months across gates and wormholes). Flaxos runs the tactical real-time simulation of a local encounter. The split is intentional: strategic decisions stay outside; tactical execution and physics stay here.

## Android/Pydroid UAT (TCP JSON)
The sim server speaks **newline-delimited JSON over TCP** (one JSON object per line). The Android UI can run in Pydroid and connect over your LAN.

### Auto-Update System
This project includes a **built-in auto-update system** that keeps your Android/Pydroid installation synchronized with the latest GitHub releases. Updates can be applied with one click from the mobile UI!

**Features:**
- Automatic update checking from GitHub releases
- One-click updates via mobile web interface
- Version management with changelog display
- Pydroid3 and APK support
- Preserves your configuration during updates

**Quick Update:**
```bash
# Check for updates (CLI)
python check_update.py --check

# Apply updates (CLI)
python check_update.py --apply

# Or use the mobile UI "System Updates" panel
```

See [`docs/ANDROID_AUTO_UPDATE.md`](docs/ANDROID_AUTO_UPDATE.md) for complete documentation.

### 1) Install dependencies in Pydroid
```bash
pip install pyyaml flask

# Optional: numpy (required for fleet formations + Phase 2 integration tests)
pip install numpy
```

**Note**: NumPy is optional. Core functionality works without it, but fleet formation features and the Phase 2 integration tests are skipped without NumPy.

### 2) Start the server (desktop recommended)
Run the sim server from your desktop/laptop so it can host the simulation loop:
```bash
python -m server.station_server --fleet-dir hybrid_fleet --dt 0.1 --host 0.0.0.0 --port 8765

# Minimal server (no stations)
# python -m server.run_server --fleet-dir hybrid_fleet --dt 0.1 --host 0.0.0.0 --port 8765
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
# In the web GUI command prompt (space-separated):
get_state
set_thrust 0.5
set_orientation 0 45 0
```

### Sensors & Targeting
```bash
ping_sensors
lock_target C001
unlock_target
```

### Autopilot
```bash
autopilot match C001
autopilot intercept C001
autopilot hold
autopilot hold_velocity
autopilot off
```

### Combat
```bash
lock_target C001
fire_weapon torpedo
fire_weapon pdc
```

### Notes
- These examples reflect the **currently implemented TCP command surface** used by the web GUI (`gui/components/command-prompt.js`).
- `get_events` is present, but event streaming/logging is not currently wired in the core simulator, so clients may see an empty event list.

## 🎮 Demo Scenarios

The simulator includes 5 playable scenarios with objectives and win/loss conditions:

### 1. **Tutorial: Intercept and Approach** (`scenarios/01_tutorial_intercept.yaml`)
**Difficulty:** ⭐ Easy
**Objective:** Learn basic navigation and autopilot systems
**Description:** Intercept Tycho Station (54km away) and close to within 1km. Perfect for learning the controls.

**Win Condition:** Close to within 1km of the station
**Time Limit:** None (training mission)

**Key Skills:**
- Using passive sensors to detect contacts
- Locking targets with the targeting system
- Engaging intercept autopilot
- Understanding autopilot phase transitions

---

### 2. **Combat: Eliminate Threat** (`scenarios/02_combat_destroy.yaml`)
**Difficulty:** ⭐⭐ Medium
**Objective:** Destroy a hostile pirate ship
**Description:** Hunt down and eliminate a pirate frigate threatening civilian traffic.

**Win Condition:** Destroy the pirate ship
**Lose Condition:** Time runs out (5 minutes)

**Key Skills:**
- Combat engagement with moving targets
- Weapon systems (torpedoes, PDC)
- Intercept course on moving target
- Time management

**Weapons:**
- 12x Torpedoes
- 1000x PDC rounds

---

### 3. **Escort: Protect the Convoy** (`scenarios/03_escort_protect.yaml`)
**Difficulty:** ⭐⭐⭐ Hard
**Objective:** Escort a civilian freighter through hostile space
**Description:** Protect the Canterbury from 2 pirate fighters for 3 minutes while staying within 10km.

**Win Condition:** Keep the freighter intact for 3 minutes
**Lose Condition:** Freighter is destroyed

**Key Skills:**
- Match velocity with escort target
- Multi-target engagement
- Defensive positioning
- Threat prioritization

**Tactical Notes:**
- Freighter moves at constant 50 m/s
- Two fast-moving fighters will approach
- Must balance protection and interception
- Optional objective: Stay within 10km

---

### 4. **Stealth: Silent Observer** (`scenarios/04_stealth_recon.yaml`)
**Difficulty:** ⭐⭐⭐⭐ Very Hard
**Objective:** Perform reconnaissance on enemy base without detection
**Description:** Approach Mars Defense Station to 50km, perform active scan, avoid detection.

**Win Condition:** Scan the station without being detected
**Lose Condition:** Detection by station or patrol ships

**Key Skills:**
- Stealth navigation (minimal thrust signature)
- Passive sensor utilization
- Timing active ping carefully
- Threat avoidance

**Critical Rules:**
- Keep thrust LOW (<0.2) to minimize signature
- Detection range ~50km with low thrust
- Active ping reveals your position!
- Patrol ships are actively searching

---

### 5. **Race: Belt Runner** (`scenarios/05_race_checkpoint.yaml`)
**Difficulty:** ⭐⭐ Medium
**Objective:** Complete checkpoint course in under 4 minutes
**Description:** Navigate through 4 checkpoints in the asteroid belt. Total distance ~256km.

**Win Condition:** Pass all checkpoints within time limit
**Lose Condition:** Miss checkpoint or time runs out

**Key Skills:**
- High-speed navigation
- Manual override of autopilot
- Fuel management
- Course optimization

**Course Layout:**
- Start → Alpha: 59km
- Alpha → Bravo: 55km
- Bravo → Charlie: 83km
- Charlie → Finish: 59km

**Record Time:** 3:45 (can you beat it?)

---

## Running Scenarios

To load a scenario (once integrated with simulator):
```python
from hybrid.scenarios.loader import ScenarioLoader

# Load scenario
scenario = ScenarioLoader.load("scenarios/01_tutorial_intercept.yaml")

# Access mission objectives
mission = scenario["mission"]
print(mission.briefing)

# Check objective status
status = mission.get_status()
```

## Latest Updates (2026-01-19)

### Quality Improvements & Technical Debt Resolution
- **Event Filtering System**: Station-based event filtering with role-specific event delivery
- **Fleet Status Reporting**: Real-time ship health assessment (online/damaged/critical/destroyed)
- **Player Hint System**: Tutorial hints integrated with event bus for better onboarding
- **Station Ship Listing**: `list_ships` command now returns live ship metadata for clients
- **Documentation**: New sprint recommendations and implementation guide

See [`docs/SPRINT_RECOMMENDATIONS.md`](docs/SPRINT_RECOMMENDATIONS.md) for complete details.

## Phase 2: Multi-Crew Station Architecture

### 🎮 Multi-Station System
Play cooperatively with multiple crew members on different stations, each with specialized roles and permissions:

**Station Types:**
- **CAPTAIN**: Full ship control, can override any station
- **HELM**: Navigation, autopilot, thrust control
- **TACTICAL**: Weapons, targeting, firing control
- **OPS**: Sensors, contacts, ECM/ECCM
- **ENGINEERING**: Power management, damage control, repairs
- **COMMS**: Fleet communications, IFF, hailing
- **FLEET_COMMANDER**: Fleet-level tactical control, formation management

**Permission Levels:**
- **CAPTAIN**: All commands, sees all events
- **OFFICER**: Station commands + cross-station visibility
- **CREW**: Station-specific commands only

**Features:**
- Role-based command authorization
- Station-specific event filtering
- Session management with automatic cleanup
- Client registration and ship assignment
- Concurrent multi-client support

### 🤖 Fleet Management & AI
- **Fleet Manager**: Coordinate multiple ships in formations
  - Line, wedge, column, and sphere formations
  - Automatic position calculation and maintenance
  - Fleet-wide command propagation

- **AI Controller**: Autonomous ship behavior
  - IDLE, PATROL, INTERCEPT, ESCORT, ATTACK modes
  - Behavior-based decision making
  - Integration with ship systems
  - Enable/disable AI per ship

### 👥 Crew Efficiency System
Realistic crew skill and fatigue simulation:

**Crew Skills:**
- PILOTING, GUNNERY, SENSORS, ENGINEERING, COMMUNICATIONS, TACTICAL
- Skill levels: Novice (40%), Skilled (70%), Expert (90%), Master (100%)
- Progressive skill improvement through experience
- Performance tracking with success rate calculation

**Fatigue System:**
- Gradual fatigue accumulation during duty (8hr full fatigue)
- Rest recovery (8hr for full recovery)
- Efficiency penalties when fatigued
- Command execution affected by crew state

**Crew Management:**
- Create and assign crew to ships
- Track performance metrics
- Station assignment with skill matching
- Real-time efficiency calculations

### 📡 Enhanced Event System
- **Station-Based Filtering**: Clients only receive relevant events for their station
- **Event Categories**: HELM, TACTICAL, OPS, ENGINEERING, COMMS, FLEET_COMMANDER
- **Universal Events**: Critical alerts, hints, and mission updates visible to all
- **Bandwidth Optimization**: Reduced network traffic through smart filtering

## What's in Sprint 2 (Previous Release)
- **Missiles/Torps/Nukes**: PN-like guidance; seeker FOV; ECM/ECCM (wider FOV + turn authority); proximity fusing; nuke AoE.
- **Point Defense**: Automatic engagement inside arc/range/FOV.
- **Server API**: `get_state`, `get_events`, `get_mission`, `fire_weapon`, `set_target`, `ping_sensors`, recording controls.
