# Changelog

All notable changes to the Flaxos Spaceship Simulator project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Stable station telemetry filter import path in `server/telemetry/station_filter.py`.
- Station telemetry filtering tests for helm/captain behavior.
- Station `list_ships` command now surfaces live ship metadata from the simulator.

### Fixed
- Captain station claims now auto-elevate permissions for override actions.
- Phase 2 integration tests no longer return values (removes pytest warnings).
- Station meta-commands can now run without requiring a ship assignment.
- Station transfer command now correctly enforces officer-or-higher permission checks.

### Planned
- Quaternion-based attitude system (Sprint S3)
- RCS thruster torque calculations (Sprint S3)
- Subsystem damage model (Sprint S4)
- Heat management system (Sprint S4)
- Advanced AI behaviors (Sprint S5)
- Replay viewer (Sprint S6)

---

## [0.2.0] - 2026-01-20 - Phase 2: Multi-Crew & Fleet

### Added - Station Control System
- **Multi-crew station architecture** with 7 station types
  - CAPTAIN: Full ship control, can override any station
  - HELM: Navigation, autopilot, thrust control
  - TACTICAL: Weapons, targeting, firing control
  - OPS: Sensors, contacts, ECM/ECCM
  - ENGINEERING: Power management, damage control
  - COMMS: Fleet communications, IFF, hailing
  - FLEET_COMMANDER: Fleet-level tactical control
- **Permission system** with 4 levels: Observer, Crew, Officer, Captain
- **Station manager** for claim/release and session tracking
- **Command dispatcher** with permission-based routing
- **Telemetry filtering** - station-specific data views
- **Event filtering** - role-based event delivery
- **Client registration** and multi-client session management
- **Heartbeat system** with automatic stale claim cleanup

### Added - Fleet Management
- **Fleet creation** and disbanding
- **Formation system** - line, wedge, column, sphere formations
- **Fleet commands** - coordinated maneuvers and targeting
- **Fleet telemetry** - aggregated status reporting
- **Ship status assessment** - online/damaged/critical/destroyed states
- **AI controller** - IDLE, PATROL, INTERCEPT, ESCORT, ATTACK behaviors

### Added - Crew Efficiency System
- **Crew creation** with skills and experience tracking
- **Fatigue system** - gradual accumulation and rest recovery
- **Skill progression** - experience-based improvement
- **Performance tracking** - success rate calculations
- **Station assignment** with skill-based matching

### Added - Scenarios & Missions
- **Hint system** - context-sensitive tutorial messages
- **Event bus integration** for hint delivery
- **5 playable scenarios**:
  1. Tutorial: Intercept and Approach
  2. Combat: Eliminate Threat
  3. Escort: Protect the Convoy
  4. Stealth: Silent Observer
  5. Race: Belt Runner

### Added - Documentation
- `docs/FEATURE_STATUS.md` - Comprehensive feature tracking
- `docs/ARCHITECTURE.md` - System architecture documentation
- `docs/KNOWN_ISSUES.md` - Known issues and limitations
- `docs/NEXT_SPRINT.md` - Sprint S3 planning
- `docs/SPRINT_RECOMMENDATIONS.md` - Sprint planning guide
- `docs/API_REFERENCE.md` - TCP JSON protocol documentation
- Updated `README.md` with Phase 2 features

### Changed
- **Server architecture** - `station_server.py` replaces basic TCP server
- **Command routing** - now goes through permission-aware dispatcher
- **Telemetry delivery** - filtered based on station permissions
- **Event delivery** - filtered based on station roles

### Fixed
- Event filtering system implementation (was TODO)
- Fleet status reporting (was placeholder)
- Player hint delivery mechanism (was console-only)

### Files Added
```
server/stations/
├── __init__.py
├── station_types.py        # Station definitions
├── station_manager.py      # Claim management
├── station_dispatch.py     # Command dispatcher
├── station_telemetry.py    # Telemetry filtering
├── station_commands.py     # Station commands
├── fleet_commands.py       # Fleet commands
├── fleet_telemetry.py      # Fleet telemetry
├── crew_system.py          # Crew management
└── README.md               # Station system docs

server/station_server.py    # Main server with stations

tests/stations/
├── test_station_types.py
├── test_station_manager.py
└── __init__.py

docs/
├── FEATURE_STATUS.md
├── ARCHITECTURE.md
├── KNOWN_ISSUES.md
├── NEXT_SPRINT.md
└── SPRINT_RECOMMENDATIONS.md
```

---

## [0.1.0] - 2026-01-15 - Phase 1: Core Systems

### Added - Core Simulation
- **Newtonian physics** - position, velocity, acceleration
- **Euler angle orientation** - pitch, yaw, roll
- **Ship entity system** - modular ship architecture
- **Fixed timestep simulation** - deterministic physics (dt=0.1s)
- **Ship factory** - JSON-based ship creation

### Added - Navigation & Autopilot
- **Navigation controller** - mode arbitration system
- **Autopilot programs**:
  - Match Velocity - PID velocity matching
  - Intercept - 3-phase lead pursuit
  - Hold Position - station keeping
  - Hold Velocity - cruise control
- **Relative motion calculations** - range, bearing, TCA, CPA
- **Collision detection** - point mass collisions

### Added - Sensors & Detection
- **Passive sensors** - continuous background scanning
- **Active sensors** - manual ping with cooldown
- **Contact management** - stable IDs (C001, C002, ...)
- **Contact classification** - Unknown → Small/Medium/Large → Full class
- **Signature calculation** - based on thrust, mass, propulsion
- **Contact aging** - confidence decay over time

### Added - Weapons & Combat
- **Torpedoes/Missiles** - proportional navigation guidance
- **Railguns** - kinetic projectiles
- **Point Defense Cannons** - automatic engagement
- **Targeting system** - lock/unlock, firing solutions
- **ECM/ECCM** - electronic countermeasures
- **Nuclear warheads** - area-of-effect damage
- **Hardpoint system** - modular weapon mounts

### Added - Power & Systems
- **Reactor system** - power generation
- **Power management** - system power allocation
- **Fuel system** - consumption, refueling
- **System health** - online/offline status tracking

### Added - Networking
- **TCP JSON server** - newline-delimited JSON protocol
- **Multi-client support** - concurrent connections
- **Command API** - comprehensive command set
- **Telemetry streaming** - real-time state snapshots
- **Event streaming** - combat and system events

### Added - Android Support
- **Pydroid3 compatibility** - runs on Android
- **Mobile UI** - Flask-based web interface
- **Auto-update system** - GitHub release synchronization
- **TCP client** - network connectivity from mobile

### Added - Testing
- **72 unit tests** - comprehensive test coverage
- **Physics tests** - kinematics, collisions
- **System tests** - weapons, sensors, navigation
- **Integration tests** - full simulation scenarios

### Added - Documentation
- `README.md` - Project overview and quickstart
- `docs/PROJECT_PLAN.md` - Development roadmap
- `docs/TUTORIAL.md` - Gameplay tutorial
- `docs/USER_GUIDE.md` - User manual
- `docs/ANDROID_AUTO_UPDATE.md` - Auto-update guide

### Files Added
```
hybrid/
├── ship.py                 # Ship entity
├── simulator.py            # Core simulation
├── ship_factory.py         # Ship creation
├── command_handler.py      # Command routing
├── telemetry.py            # Telemetry generation
├── systems/                # Ship systems
│   ├── weapons/
│   ├── sensors/
│   ├── navigation/
│   └── power/
├── navigation/             # Autopilot
├── fleet/                  # Fleet management (basic)
└── scenarios/              # Mission system

server/
└── run_server.py           # Basic TCP server

tests/
├── systems/
├── hybrid_tests/
└── core/
```

---

## [0.0.1] - 2025-12-01 - Initial Prototype

### Added
- Basic physics simulation
- Simple ship movement
- Proof-of-concept code

---

## Version History Summary

| Version | Date | Description |
|---------|------|-------------|
| 0.2.0 | 2026-01-20 | Phase 2: Multi-crew & Fleet |
| 0.1.0 | 2026-01-15 | Phase 1: Core Systems |
| 0.0.1 | 2025-12-01 | Initial Prototype |

---

## Migration Guides

### Migrating from 0.1.0 to 0.2.0

**Server Changes:**
- Old server: `python -m server.run_server`
- New server: `python -m server.station_server`

**Connection Flow:**
```python
# Old: Direct ship commands
{"cmd": "set_thrust", "ship": "ship_001", "thrust": 0.5}

# New: Register, assign, claim, then command
{"cmd": "assign_ship", "ship": "ship_001"}
{"cmd": "claim_station", "station": "helm"}
{"cmd": "set_thrust", "thrust": 0.5}  # ship_id inferred from session
```

**Telemetry:**
- Telemetry is now filtered based on claimed station
- Use `get_state` to get filtered telemetry for your station
- Captain sees all telemetry, other stations see relevant data only

**Backward Compatibility:**
- Old server (`run_server.py`) still works for single-player
- Commands work as before (ship_id can be explicit)
- Telemetry format unchanged (but filtered in multi-crew mode)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

---

## Links

- **Repository**: https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01
- **Issues**: https://github.com/flaxos/Flaxos-Spaceshi_-Sim_0.01/issues
- **Documentation**: See `docs/` directory
- **Roadmap**: See `docs/PROJECT_PLAN.md`

---

**Changelog Maintained By**: Development Team
**Last Updated**: 2026-01-20
