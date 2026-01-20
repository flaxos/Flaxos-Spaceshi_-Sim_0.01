# Physics Update Notes — Quaternion Attitude & RCS Torque (Sprint S3)

**Version**: 0.5.0
**Last Updated**: 2026-01-20

---

## Purpose

This document captures the physics updates planned for Sprint S3: the transition from Euler angles to quaternions for ship attitude, plus torque-based angular dynamics driven by RCS thrusters. It is intended to guide implementation work in `hybrid/ship.py`, `hybrid/systems/rcs_system.py`, and related telemetry/autopilot modules.

---

## Current State (Pre-S3)

- Orientation is stored as Euler angles in `Ship.orientation` (pitch, yaw, roll).
- Angular velocity is tracked per-axis in degrees per second.
- Quaternion math utilities are implemented in `hybrid/utils/quaternion.py`.
- RCS thruster configuration is documented in `docs/RCS_CONFIGURATION_GUIDE.md`.

---

## Planned Changes

### 1) Quaternion Attitude State

**Goal:** Add `Ship.quaternion` as the authoritative attitude state, while keeping Euler angles for telemetry and legacy command inputs.

**Key decisions:**
- Euler angles remain supported for command inputs (e.g., heading, pitch, yaw).
- Telemetry continues to report Euler angles for UI display.
- Quaternions are normalized after each integration step to prevent drift.

**Integration sketch:**
```python
# In Ship.__init__
self.orientation = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
self.quaternion = Quaternion.from_euler(0.0, 0.0, 0.0)

# In Ship._update_physics
omega = Quaternion(0, omega_x, omega_y, omega_z)
q_dot = 0.5 * self.quaternion * omega
self.quaternion = self.quaternion + q_dot * dt
self.quaternion.normalize()

# Keep Euler telemetry in sync
pitch, yaw, roll = self.quaternion.to_euler()
self.orientation.update({"pitch": pitch, "yaw": yaw, "roll": roll})
```

### 2) Torque-Based Angular Dynamics

**Goal:** Drive angular acceleration from RCS torque instead of direct Euler velocity changes.

**Core formula:**
- **Torque:** τ = r × F
- **Angular acceleration:** α = τ / I

**Integration sketch:**
```python
# In Ship._update_physics
rcs_torque = self.systems.get("rcs").get_total_torque() if "rcs" in self.systems else np.zeros(3)
angular_accel = rcs_torque / self.moment_of_inertia

self.angular_velocity["pitch"] += angular_accel[0] * dt
self.angular_velocity["yaw"] += angular_accel[1] * dt
self.angular_velocity["roll"] += angular_accel[2] * dt
```

### 3) RCS Thruster Allocation

**Goal:** The RCS system determines thruster output levels to achieve desired angular velocity targets.

**Key behaviors:**
- Thruster torque contribution is computed from per-thruster position and force direction.
- Allocation is currently heuristic; optimization can follow later.
- Fuel use is proportional to thruster level and `dt`.

**Reference:** `docs/RCS_CONFIGURATION_GUIDE.md`

---

## Telemetry & API Considerations

- Telemetry continues to expose Euler angles in `orientation` for compatibility.
- Consider adding a `quaternion` field to telemetry for advanced clients (opt-in).
- Command handlers that accept Euler angles should update the quaternion state via `Quaternion.from_euler()`.

---

## Testing & Validation Checklist

**Unit tests**
- Quaternion integration accuracy for small rotations
- Quaternion → Euler → quaternion round-trip checks
- Torque integration and angular acceleration correctness

**Integration tests**
- Full rotation using RCS thrusters
- Autopilot pointing accuracy with quaternion attitude
- Edge cases: pitch = ±90° (no gimbal lock)

**Performance checks**
- Compare tick timing before/after quaternion integration
- Ensure normalization does not cause numerical instability

---

## Rollout Checklist

1. Add `Ship.quaternion` + update physics integration.
2. Update `Ship.set_heading()` and autopilot programs to use quaternions.
3. Implement `hybrid/systems/rcs_system.py` and ship configs.
4. Add torque integration + fuel consumption tracking.
5. Extend telemetry tests to validate Euler + quaternion sync.

---

## References

- `docs/QUATERNION_API.md`
- `docs/RCS_CONFIGURATION_GUIDE.md`
- `hybrid/utils/quaternion.py`
