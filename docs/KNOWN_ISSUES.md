# Known Issues & Limitations

**Project**: Flaxos Spaceship Simulator
**Version**: 0.2.0
**Last Updated**: 2026-01-20

---

## Critical Issues

*None currently identified*

All critical bugs have been resolved as of Phase 2 completion.

---

## High Priority Issues

### 1. Gimbal Lock in Euler Angle System
**Status**: 🔴 Known Limitation
**Severity**: High (Physics accuracy)
**Affected Components**: `hybrid/ship.py`, orientation calculations
**Planned Fix**: Sprint S3 (Quaternion implementation)

**Description:**
The current orientation system uses Euler angles (pitch, yaw, roll) which can experience gimbal lock at extreme orientations (e.g., pitch = ±90°).

**Impact:**
- Unpredictable rotation behavior near vertical orientations
- Difficult to maintain stable attitude control at extreme angles
- Autopilot may become unstable in edge cases

**Workaround:**
Avoid sustained operations at pitch angles near ±90°

**Resolution Plan:**
Sprint S3 will implement quaternion-based attitude representation, completely eliminating gimbal lock.

**Files to Change:**
- `hybrid/ship.py` - Add quaternion state
- `hybrid/utils/quaternion.py` - New quaternion math library
- `hybrid/navigation/` - Update autopilot to use quaternions

---

## Medium Priority Issues

### 2. NumPy Dependency for Fleet Formations
**Status**: ⚠️ Limitation
**Severity**: Medium (Feature availability)
**Affected Components**: `hybrid/fleet/formation.py`

**Description:**
Fleet formation calculations require NumPy for matrix operations. This is marked as optional in dependencies but fleet formation commands will fail without it.

**Impact:**
- Fleet formation commands unavailable without NumPy
- Android/Pydroid users must manually install NumPy
- Core functionality works, but fleet features limited

**Workaround:**
```bash
pip install numpy
```

**Potential Solutions:**
1. Implement formation math using pure Python lists (slower)
2. Make fleet formations completely optional
3. Document NumPy as recommended (current approach)

---

### 3. No Replay Viewer
**Status**: 🔴 Missing Feature
**Severity**: Medium (Quality of life)
**Affected Components**: Recording system
**Planned**: Sprint S6

**Description:**
The simulator can record game sessions to JSON, but there's no replay viewer to playback recordings.

**Impact:**
- Cannot review tactical decisions after battle
- Difficult to debug physics issues retroactively
- No way to create gameplay videos from recordings

**Current State:**
- Recording works: `{"cmd": "record_start"}`
- Data is saved correctly
- No playback mechanism exists

**Planned Features:**
- Replay viewer with timeline scrubbing
- Speed controls (1x, 2x, 0.5x)
- Camera controls for cinematic views
- Export to video

---

### 4. Limited AI Behaviors
**Status**: ⚠️ Incomplete
**Severity**: Medium (Gameplay depth)
**Affected Components**: `hybrid/fleet/ai_controller.py`

**Description:**
AI controller has only basic behaviors:
- IDLE - Do nothing
- PATROL - Move in circles
- INTERCEPT - Chase target
- ESCORT - Follow target
- ATTACK - Engage with weapons

**Missing Behaviors:**
- Evasive maneuvers
- Formation keeping
- Target prioritization
- Ammunition management
- Retreat conditions
- Cooperative tactics

**Planned**: Sprint S5 (Advanced AI)

---

## Low Priority Issues

### 5. No Subsystem Damage Model
**Status**: 🔴 Missing Feature
**Severity**: Low (Future enhancement)
**Affected Components**: Damage system
**Planned**: Sprint S4

**Description:**
Ships have overall health but no individual subsystem damage:
- Cannot target specific systems (engines, weapons, sensors)
- No cascading failures
- No repair prioritization

**Current Behavior:**
- Ships are either functional or destroyed
- System status is binary (online/offline)
- No partial degradation

**Planned Implementation:**
```python
class DamageModel:
    subsystems = {
        "reactor": {"health": 100, "critical": True},
        "propulsion": {"health": 100, "degradation": True},
        "sensors": {"health": 100},
        # ...
    }

    def apply_damage(self, system: str, amount: float):
        # Reduce system health
        # Check for cascading failures
        # Update ship capabilities
```

---

### 6. No Heat Management
**Status**: 🔴 Missing Feature
**Severity**: Low (Realism)
**Affected Components**: Power and weapons systems
**Planned**: Sprint S4

**Description:**
No heat generation or dissipation mechanics. Ships can fire weapons and run systems indefinitely without overheating.

**Planned Features:**
- Heat generation from reactor, weapons, propulsion
- Radiator systems for heat dissipation
- Overheating effects (system shutdowns, reduced efficiency)
- Thermal signature for stealth gameplay

---

### 7. No Crew Injuries/Death
**Status**: 🔴 Missing Feature
**Severity**: Low (Immersion)
**Affected Components**: `server/stations/crew_system.py`
**Planned**: Sprint S4

**Description:**
Crew members have fatigue and skills but cannot be injured or killed. Combat has no impact on crew beyond ship destruction.

**Planned Features:**
- Injury from combat damage
- Medical system
- Crew replacement mechanics
- Morale system

---

## Performance Issues

### 8. No Performance Benchmarks
**Status**: ⚠️ Monitoring Needed
**Severity**: Low (Optimization)

**Description:**
No systematic performance benchmarks or profiling data.

**Current Metrics:**
- Tested: 10 ships at 10 Hz tick rate
- CPU usage: ~5% idle, ~15% active (estimated)
- No formal stress testing

**Needed:**
- Automated performance benchmarks
- Memory usage tracking
- Network bandwidth measurements
- Scalability testing (50+ ships)

---

## Platform-Specific Issues

### 9. Android GUI Limitations
**Status**: ⚠️ Expected Limitation
**Severity**: Low (Platform constraint)
**Affected Components**: `hybrid/gui/`

**Description:**
Desktop GUI (Tkinter) and rendering (Pygame) don't work on Android/Pydroid.

**Impact:**
- Android users must use mobile_ui (Flask) or custom clients
- No graphical HUD on mobile

**Solution:**
This is by design. The Flask-based mobile UI is the recommended interface for Android.

---

### 10. Pydroid Server Performance
**Status**: ⚠️ Expected Limitation
**Severity**: Low (Device constraint)

**Description:**
Running the simulation server on Android devices may have reduced performance compared to desktop.

**Recommendations:**
- Host server on desktop when possible
- Reduce tick rate on mobile (`--dt 0.2` or higher)
- Limit fleet size on mobile servers

---

## Testing Gaps

### 11. No Network Stress Testing
**Status**: ⚠️ Testing Gap
**Severity**: Medium (Reliability)

**Description:**
Limited testing of network edge cases:
- No tests for connection drops
- No tests for high latency
- No tests for packet loss
- No tests for concurrent multi-client scenarios

**Planned**: Sprint S6 (Network robustness)

---

### 12. No Continuous Integration
**Status**: 🔴 Missing Infrastructure
**Severity**: Low (Development workflow)
**Planned**: Sprint S6

**Description:**
No CI/CD pipeline for automated testing.

**Impact:**
- Manual test execution required
- No automated regression detection
- No coverage reporting

**Planned Setup:**
- GitHub Actions for automated tests
- Coverage reporting with codecov
- Lint checks (flake8, black)
- Automated release builds

---

## Documentation Gaps

### 13. No Video Tutorials
**Status**: 🔴 Missing Content
**Severity**: Low (Onboarding)

**Description:**
Documentation is text-based only. No video tutorials or gameplay demonstrations.

**Needed:**
- Getting started video
- Multi-crew coordination demo
- Combat tactics tutorial
- Fleet coordination example

---

## False Positives / Non-Issues

### Items Previously Reported as Issues (Now Resolved)

1. **Event Filtering** - ✅ Resolved in Sprint (2026-01-19)
2. **Fleet Status Reporting** - ✅ Resolved in Sprint (2026-01-19)
3. **Player Hints** - ✅ Resolved in Sprint (2026-01-19)

---

## Issue Tracking

### Reporting New Issues

**For Bugs:**
1. Check this document first
2. Verify issue with latest code
3. Create GitHub issue with:
   - Steps to reproduce
   - Expected vs actual behavior
   - System info (OS, Python version)
   - Relevant logs

**For Feature Requests:**
1. Check roadmap in `PROJECT_PLAN.md`
2. Check `NEXT_SPRINT.md` for planned features
3. Open GitHub issue with:
   - Use case description
   - Proposed implementation (optional)
   - Priority justification

---

## Priority Definitions

- 🔴 **Critical**: Crashes, data loss, security issues → Fix immediately
- ⚠️ **High**: Major functionality broken → Fix next sprint
- 🟡 **Medium**: Feature limitation or degradation → Planned fix
- 🟢 **Low**: Minor issue or enhancement → Future consideration

---

## Resolution Timeline

### Current Sprint (2026-01-20)
- ✅ All critical issues resolved
- ✅ Documentation completed

### Next Sprint (S3 - Quaternion Attitude)
- 🎯 Issue #1: Gimbal lock → Quaternion implementation
- 🎯 Improve performance benchmarking

### Future Sprints
- S4: Issues #5, #6, #7 (Damage, heat, crew injuries)
- S5: Issue #4 (Advanced AI)
- S6: Issues #3, #11, #12 (Replay, network, CI/CD)

---

## Workaround Summary

| Issue | Workaround |
|-------|------------|
| Gimbal lock | Avoid pitch ±90° |
| No NumPy | `pip install numpy` |
| No replay viewer | Use logs for debugging |
| Limited AI | Manual fleet control |
| No subsystem damage | Accept binary ship states |
| Android GUI | Use mobile_ui Flask app |

---

## Change Log

**2026-01-20**: Initial creation
- Documented 13 known issues
- Categorized by priority
- Added resolution plans

---

**Document Status**: Active
**Maintained By**: Development Team
**Review Frequency**: After each sprint
