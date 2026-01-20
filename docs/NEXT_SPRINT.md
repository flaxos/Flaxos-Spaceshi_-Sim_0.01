# Next Sprint Plan - S3: Quaternion Attitude & RCS Torque

**Sprint**: S3 (Attitude System Overhaul)
**Duration**: 4-6 weeks
**Priority**: HIGH
**Status**: 📋 Planning Phase

---

## Sprint Overview

Sprint S3 focuses on replacing the Euler angle orientation system with quaternion-based attitude representation and implementing realistic RCS (Reaction Control System) torque calculations. This is a foundational change that enables:

1. **Elimination of gimbal lock** - Stable attitude control at all orientations
2. **Realistic torque physics** - RCS thrusters generate actual torque
3. **Improved aim fidelity** - Weapon pointing accuracy
4. **Foundation for Sprint S4** - Advanced combat mechanics

**Recent Updates**
- Added a stable telemetry filter import path (`server/telemetry/station_filter.py`) and tests to validate station-scoped filtering. Keep this module updated if telemetry logic changes.
- Captain station claims now auto-elevate permissions for cross-station overrides.
- Station management `list_ships` now returns live ship metadata via the station server.
- Station transfer now enforces officer-or-higher permissions.
- Published quaternion API documentation (`docs/QUATERNION_API.md`).

---

## Sprint Goals

### Primary Objectives
1. ✅ Implement quaternion mathematics library
2. ✅ Integrate quaternion attitude into Ship class
3. ✅ Configure RCS thruster system
4. ✅ Calculate torque from RCS thrusters
5. ✅ Update autopilot to use quaternions
6. ✅ Maintain backward compatibility with Euler angles

### Success Criteria
- [ ] All existing tests pass with quaternion system
- [ ] No gimbal lock at any orientation
- [ ] RCS thrusters generate realistic torque
- [ ] Autopilot works with quaternion attitude
- [ ] Performance impact < 10% vs current system
- [ ] 90%+ test coverage for new code

---

## Sprint Phases

### Phase A: Quaternion Foundation (Week 1-2)

#### Deliverable: Quaternion Math Library
**File**: `hybrid/utils/quaternion.py`

**Required Functions:**
```python
class Quaternion:
    """Quaternion for 3D rotations"""

    def __init__(self, w, x, y, z):
        """Create quaternion from components"""

    @classmethod
    def from_euler(cls, pitch, yaw, roll):
        """Create from Euler angles (degrees)"""

    @classmethod
    def from_axis_angle(cls, axis, angle):
        """Create from axis-angle representation"""

    def to_euler(self):
        """Extract Euler angles (degrees)"""

    def normalize(self):
        """Normalize to unit quaternion"""

    def conjugate(self):
        """Conjugate (inverse for unit quaternions)"""

    def __mul__(self, other):
        """Quaternion multiplication (composition)"""

    def rotate_vector(self, v):
        """Rotate vector by this quaternion"""

    @staticmethod
    def slerp(q1, q2, t):
        """Spherical linear interpolation"""

    def to_rotation_matrix(self):
        """Convert to 3x3 rotation matrix"""
```

**Test Coverage:**
- [ ] 20+ unit tests for all operations
- [ ] Edge cases: (0,0,0), (0,0,90), (90,0,0), (0,90,0)
- [ ] Gimbal lock angles: pitch = ±90°
- [ ] Numerical stability tests
- [ ] Identity quaternion behavior
- [ ] Quaternion composition accuracy
- [ ] SLERP interpolation correctness

**Validation:**
Compare quaternion → Euler → quaternion conversions for accuracy.

---

### Phase B: Ship Integration (Week 2-3)

#### Deliverable: Quaternion-Based Ship Attitude
**Files Modified:**
- `hybrid/ship.py` - Add quaternion state
- `hybrid/ship_factory.py` - Initialize quaternions from ship definitions

**Changes Required:**

1. **Add Quaternion State**
```python
class Ship:
    def __init__(self, ...):
        # Keep Euler for backward compatibility
        self.orientation = {"pitch": 0, "yaw": 0, "roll": 0}

        # Add quaternion state
        self.quaternion = Quaternion.from_euler(0, 0, 0)
```

2. **Update Physics Loop**
```python
def _update_physics(self, dt):
    # Integrate angular velocity using quaternion derivative
    # q' = 0.5 * q * ω (quaternion form)

    omega_quat = Quaternion(0, omega_x, omega_y, omega_z)
    q_dot = 0.5 * self.quaternion * omega_quat
    self.quaternion = self.quaternion + q_dot * dt
    self.quaternion.normalize()

    # Sync Euler angles for telemetry
    self.orientation = self.quaternion.to_euler()
```

3. **Update Bearing Calculations**
```python
def calculate_bearing_to(self, target_pos):
    # Use quaternion to rotate world vector to ship frame
    world_to_target = target_pos - self.position
    ship_frame_target = self.quaternion.conjugate().rotate_vector(world_to_target)

    # Calculate pitch and yaw in ship frame
    bearing = math.atan2(ship_frame_target[1], ship_frame_target[0])
    elevation = math.atan2(ship_frame_target[2], ...)
```

**Test Coverage:**
- [ ] Quaternion integration accuracy
- [ ] Euler angle sync correctness
- [ ] No gimbal lock at extreme angles
- [ ] Bearing calculations match old system
- [ ] Orientation commands still work

**Backward Compatibility:**
- Commands using Euler angles (heading, pitch, yaw) still work
- Telemetry reports Euler angles for display
- Internally use quaternions for physics

---

### Phase C: RCS Thruster System (Week 3-4)

#### Deliverable: RCS Thruster Configuration
**Files Created:**
- `hybrid/systems/rcs_system.py` - RCS thruster system
- `hybrid_fleet/ship_configs/rcs_*.yaml` - RCS configurations

**YAML Configuration Format:**
```yaml
# hybrid_fleet/ship_configs/frigate_rcs.yaml
systems:
  rcs:
    enabled: true
    fuel_type: "rcs_propellant"
    thrusters:
      # Bow thrusters (yaw control)
      - id: "bow_port"
        position: [10.0, -5.0, 0.0]   # m from center of mass
        direction: [0.0, 1.0, 0.0]     # thrust vector (normalized)
        max_thrust: 1000.0             # Newtons
        fuel_consumption: 0.1          # kg/s at max thrust

      - id: "bow_starboard"
        position: [10.0, 5.0, 0.0]
        direction: [0.0, -1.0, 0.0]
        max_thrust: 1000.0
        fuel_consumption: 0.1

      # Stern thrusters (yaw control)
      - id: "stern_port"
        position: [-10.0, -5.0, 0.0]
        direction: [0.0, -1.0, 0.0]
        max_thrust: 1000.0
        fuel_consumption: 0.1

      - id: "stern_starboard"
        position: [-10.0, 5.0, 0.0]
        direction: [0.0, 1.0, 0.0]
        max_thrust: 1000.0
        fuel_consumption: 0.1

      # Dorsal/ventral thrusters (pitch control)
      - id: "dorsal_bow"
        position: [8.0, 0.0, 3.0]
        direction: [0.0, 0.0, -1.0]
        max_thrust: 800.0
        fuel_consumption: 0.08

      - id: "ventral_bow"
        position: [8.0, 0.0, -3.0]
        direction: [0.0, 0.0, 1.0]
        max_thrust: 800.0
        fuel_consumption: 0.08

      # Roll thrusters (port/starboard sides)
      - id: "port_roll_fwd"
        position: [5.0, -6.0, 2.0]
        direction: [0.0, 0.0, -1.0]
        max_thrust: 500.0
        fuel_consumption: 0.05

      - id: "starboard_roll_fwd"
        position: [5.0, 6.0, -2.0]
        direction: [0.0, 0.0, 1.0]
        max_thrust: 500.0
        fuel_consumption: 0.05
```

**RCS System Implementation:**
```python
class RCSThruster:
    """Individual RCS thruster"""
    def __init__(self, config: Dict):
        self.id = config["id"]
        self.position = np.array(config["position"])  # m from CoM
        self.direction = np.array(config["direction"])  # unit vector
        self.max_thrust = config["max_thrust"]  # N
        self.fuel_consumption = config["fuel_consumption"]  # kg/s
        self.current_level = 0.0  # 0-1

    def calculate_torque(self) -> np.ndarray:
        """Calculate torque: τ = r × F"""
        force = self.direction * (self.max_thrust * self.current_level)
        torque = np.cross(self.position, force)
        return torque


class RCSSystem:
    """Reaction Control System"""
    def __init__(self, ship, config: Dict):
        self.ship = ship
        self.thrusters = [
            RCSThruster(t_config)
            for t_config in config.get("thrusters", [])
        ]
        self.enabled = config.get("enabled", True)

    def set_desired_angular_velocity(self, target_omega: Dict):
        """
        Calculate thruster levels to achieve target angular velocity.

        Args:
            target_omega: {"pitch": deg/s, "yaw": deg/s, "roll": deg/s}
        """
        # Convert target to torque needed
        current_omega = self.ship.angular_velocity
        omega_error = {
            "pitch": target_omega["pitch"] - current_omega["pitch"],
            "yaw": target_omega["yaw"] - current_omega["yaw"],
            "roll": target_omega["roll"] - current_omega["roll"],
        }

        # Simple proportional control (can be improved with PID)
        needed_torque = np.array([
            omega_error["pitch"] * self.ship.moment_of_inertia,
            omega_error["yaw"] * self.ship.moment_of_inertia,
            omega_error["roll"] * self.ship.moment_of_inertia,
        ])

        # Allocate thrusters to generate needed torque
        self._allocate_thrusters(needed_torque)

    def _allocate_thrusters(self, needed_torque: np.ndarray):
        """
        Determine thruster levels to achieve needed torque.

        This is a simplified allocation - production version would use
        optimization to minimize fuel consumption.
        """
        # Reset all thrusters
        for thruster in self.thrusters:
            thruster.current_level = 0.0

        # Simple heuristic allocation
        # (Production: use linear programming for optimal allocation)

        # For each axis, find thrusters that contribute
        for thruster in self.thrusters:
            torque_vector = thruster.calculate_torque()

            # Check if this thruster helps with needed torque
            dot_product = np.dot(torque_vector, needed_torque)
            if dot_product > 0:
                # This thruster helps - activate it
                thruster.current_level = min(1.0, dot_product / thruster.max_thrust)

    def get_total_torque(self) -> np.ndarray:
        """Get total torque from all active thrusters"""
        total_torque = np.zeros(3)
        for thruster in self.thrusters:
            total_torque += thruster.calculate_torque()
        return total_torque

    def update(self, dt: float):
        """Update RCS system"""
        if not self.enabled:
            return

        # Consume fuel
        for thruster in self.thrusters:
            if thruster.current_level > 0:
                fuel_used = thruster.fuel_consumption * thruster.current_level * dt
                self.ship.fuel -= fuel_used

    def get_telemetry(self) -> Dict:
        """Return RCS status"""
        return {
            "enabled": self.enabled,
            "thrusters": [
                {
                    "id": t.id,
                    "level": t.current_level,
                    "torque": t.calculate_torque().tolist(),
                }
                for t in self.thrusters
            ],
            "total_torque": self.get_total_torque().tolist(),
        }
```

**Test Coverage:**
- [ ] RCS configuration loading
- [ ] Torque calculation accuracy
- [ ] Thruster allocation logic
- [ ] Fuel consumption tracking
- [ ] Multiple thruster interaction

---

### Phase D: Physics Integration (Week 4-5)

#### Deliverable: Torque-Based Angular Dynamics
**Files Modified:**
- `hybrid/ship.py` - Integrate RCS torque into physics

**Changes Required:**

1. **Add Moment of Inertia**
```python
class Ship:
    def __init__(self, ...):
        # Moment of inertia (kg·m²) - estimated from ship dimensions
        # I = mass * (length² + width²) / 12  (for rectangular approximation)
        self.moment_of_inertia = self._calculate_moi()

    def _calculate_moi(self):
        """Calculate moment of inertia from ship geometry"""
        # Simplified: assume uniform density rectangular prism
        length = 50.0  # m (from ship class)
        width = 20.0   # m
        return self.mass * (length**2 + width**2) / 12.0
```

2. **Update Angular Dynamics**
```python
def _update_physics(self, dt):
    # Get torque from RCS
    if "rcs" in self.systems:
        rcs_torque = self.systems["rcs"].get_total_torque()
    else:
        rcs_torque = np.zeros(3)

    # Calculate angular acceleration: α = τ / I
    angular_accel = rcs_torque / self.moment_of_inertia

    # Update angular velocity: ω = ω + α·dt
    self.angular_velocity["pitch"] += angular_accel[0] * dt
    self.angular_velocity["yaw"] += angular_accel[1] * dt
    self.angular_velocity["roll"] += angular_accel[2] * dt

    # Apply damping (optional - space has no friction, but RCS can stabilize)
    damping = 0.95
    self.angular_velocity["pitch"] *= damping
    self.angular_velocity["yaw"] *= damping
    self.angular_velocity["roll"] *= damping

    # Integrate quaternion
    # ... (from Phase B)
```

3. **Update Heading Command**
```python
def set_heading(self, target_pitch, target_yaw):
    """Command ship to point in direction"""
    # Calculate target quaternion
    target_quat = Quaternion.from_euler(target_pitch, target_yaw, 0)

    # Calculate rotation needed
    current_quat = self.quaternion
    delta_quat = target_quat * current_quat.conjugate()

    # Convert to angular velocity command
    # (RCS system will handle thruster allocation)
    axis, angle = delta_quat.to_axis_angle()
    angular_velocity_command = axis * (angle / 1.0)  # Proportional control

    # Command RCS
    if "rcs" in self.systems:
        self.systems["rcs"].set_desired_angular_velocity({
            "pitch": angular_velocity_command[0],
            "yaw": angular_velocity_command[1],
            "roll": angular_velocity_command[2],
        })
```

**Test Coverage:**
- [ ] Torque produces correct angular acceleration
- [ ] Angular velocity integrates correctly
- [ ] Quaternion updates from angular velocity
- [ ] Heading commands work with RCS
- [ ] Fuel consumption during rotation

---

### Phase E: Autopilot Update (Week 5-6)

#### Deliverable: Quaternion-Aware Autopilot
**Files Modified:**
- `hybrid/navigation/autopilot/base.py`
- `hybrid/navigation/autopilot/intercept.py`
- `hybrid/navigation/autopilot/match_velocity.py`

**Changes Required:**

Update autopilot programs to use quaternion-based calculations:

```python
class InterceptAutopilot:
    def calculate_desired_orientation(self, ship, target_pos):
        """Calculate orientation to point at target"""
        # Vector from ship to target
        to_target = target_pos - ship.position
        to_target_normalized = to_target / np.linalg.norm(to_target)

        # Current forward vector (from quaternion)
        forward = ship.quaternion.rotate_vector([1, 0, 0])

        # Calculate rotation axis and angle
        axis = np.cross(forward, to_target_normalized)
        angle = np.arccos(np.clip(np.dot(forward, to_target_normalized), -1, 1))

        # Create target quaternion
        target_quat = Quaternion.from_axis_angle(axis, angle) * ship.quaternion

        # Convert to Euler for command interface (temporary)
        target_euler = target_quat.to_euler()

        return target_euler
```

**Test Coverage:**
- [ ] Autopilot programs work with quaternions
- [ ] No gimbal lock during autopilot
- [ ] Smooth transitions between orientations
- [ ] Intercept autopilot accuracy maintained

---

## Testing Strategy

### Unit Tests
- [ ] Quaternion math (20+ tests)
- [ ] RCS thruster calculations (10+ tests)
- [ ] Torque integration (5+ tests)
- [ ] Autopilot with quaternions (10+ tests)

### Integration Tests
- [ ] Full ship rotation using RCS
- [ ] Autopilot from any orientation
- [ ] Gimbal lock scenarios (pitch = ±90°)
- [ ] Performance benchmarks

### Regression Tests
- [ ] All existing tests pass
- [ ] Telemetry format unchanged
- [ ] Commands work as before
- [ ] Scenarios still playable

---

## Performance Targets

| Metric | Current | Target | Max Acceptable |
|--------|---------|--------|----------------|
| Tick time | 10 ms | 11 ms | 15 ms |
| CPU usage | 15% | 17% | 20% |
| Memory | 50 MB | 55 MB | 70 MB |

---

## Risks & Mitigation

### Risk 1: Quaternion Math Bugs
**Likelihood**: Medium
**Impact**: High (Physics accuracy)
**Mitigation**:
- Extensive unit tests
- Validate against known implementations (scipy.spatial.transform)
- Test edge cases thoroughly

### Risk 2: Performance Degradation
**Likelihood**: Low
**Impact**: Medium
**Mitigation**:
- Profile before and after
- Optimize hot paths
- Consider C extension if needed

### Risk 3: Breaking Changes
**Likelihood**: Medium
**Impact**: High (Existing functionality)
**Mitigation**:
- Maintain backward compatibility
- Incremental rollout (quaternions alongside Euler)
- Regression test suite

---

## Dependencies

### Required
- NumPy (already used for physics)
- Python 3.8+ (for dataclasses, type hints)

### Optional
- scipy (for validation only, not runtime)

---

## Deliverables Checklist

### Code
- [ ] `hybrid/utils/quaternion.py` - Quaternion math library
- [ ] `hybrid/systems/rcs_system.py` - RCS system
- [ ] `hybrid/ship.py` - Quaternion integration
- [ ] `hybrid_fleet/ship_configs/*_rcs.yaml` - RCS configurations

### Tests
- [ ] `tests/utils/test_quaternion.py` - 20+ tests
- [ ] `tests/systems/test_rcs_system.py` - 10+ tests
- [ ] `tests/hybrid_tests/test_quaternion_physics.py` - Integration tests
- [ ] Regression tests all passing

### Documentation
- [x] Quaternion API documentation
- [ ] RCS configuration guide
- [ ] Physics update documentation
- [ ] Migration guide (Euler → Quaternion)

---

## Sprint Timeline

**Week 1**: Quaternion math library + tests
**Week 2**: Ship integration + validation
**Week 3**: RCS system design + implementation
**Week 4**: Physics integration + testing
**Week 5**: Autopilot updates
**Week 6**: Integration testing + documentation

---

## Success Metrics

- [ ] Zero gimbal lock incidents in any orientation
- [ ] RCS fuel consumption matches physical expectations
- [ ] All 72+ existing tests pass
- [ ] 20+ new tests for quaternion/RCS
- [ ] Performance impact < 10%
- [ ] Documentation complete

---

## Post-Sprint Actions

1. Deploy to staging environment
2. User acceptance testing
3. Performance profiling
4. Update README with quaternion features
5. Plan Sprint S4 (Damage Model)

---

**Document Status**: Planning
**Sprint Start**: TBD
**Sprint End**: TBD (6 weeks from start)
**Maintained By**: Development Team
