# Coordinate Frames Reference

**Version**: 0.6.0
**Last Updated**: 2026-01-24

## Overview

This document defines the coordinate frame conventions used throughout Flaxos Spaceship Sim. Consistent coordinate frames are critical for:

- Main drive thrust direction
- RCS thruster placement and torque calculation
- Autopilot heading commands
- GUI controls and displays

## Ship Body Frame (Ship-Local)

The **ship body frame** is fixed to the spacecraft with origin at the center of mass.

```
        +Z (dorsal)
           ↑
           │
           │
    ←──────┼──────→ +X (forward/bow)
   +Y      │      -Y
(starboard)│     (port)
           │
           ↓
        -Z (ventral)
```

### Axes

| Axis | Direction | Description |
|------|-----------|-------------|
| +X | Forward | Bow (nose) direction; main drive thrust acts along this axis |
| -X | Aft | Stern direction; engine exhaust points this way |
| +Y | Starboard | Right side when looking forward |
| -Y | Port | Left side when looking forward |
| +Z | Dorsal | "Up" relative to deck; top of ship |
| -Z | Ventral | "Down" relative to deck; bottom of ship |

### Main Drive Thrust

The main drive (Epstein drive / fusion engine) produces thrust **only along the +X axis** in ship frame:

```
Force_ship = [throttle × max_thrust, 0, 0]
```

This force is then rotated to world frame using the ship's quaternion attitude before being applied as acceleration.

## World Frame (Inertial)

The **world frame** is a global inertial reference frame used for positions, velocities, and accelerations in the simulation.

- Origin: Arbitrary (typically scenario-defined)
- Axes: Fixed (do not rotate with any ship)
- Units: Meters (position), m/s (velocity), m/s² (acceleration)

## Euler Angles (Attitude)

Attitude is expressed as Euler angles for user interfaces while quaternions are used internally for physics.

| Angle | Axis | Range | Description |
|-------|------|-------|-------------|
| Pitch | Y-axis rotation | -90° to +90° | Nose up (+) / down (-) |
| Yaw | Z-axis rotation | 0° to 360° | Nose left/right |
| Roll | X-axis rotation | -180° to +180° | Rotation around forward axis |

### Euler Convention

We use **intrinsic ZYX** rotation order (aerospace convention):
1. Yaw around Z
2. Pitch around Y
3. Roll around X

### Quaternion Usage

Internally, `Ship.quaternion` is the authoritative attitude representation:
- Eliminates gimbal lock
- Smooth interpolation (SLERP)
- Efficient rotation of vectors

Euler angles in `Ship.orientation` are synced from quaternion after each physics tick for telemetry and UI display.

## RCS Thruster Configuration

RCS thrusters are defined in ship body frame with:

- `position`: [x, y, z] meters from center of mass
- `direction`: [x, y, z] unit vector of thrust direction
- `max_thrust`: Newtons at full throttle

### Torque Calculation

Thruster torque is computed as:

```
τ = r × F
```

Where:
- `r` = position vector (ship frame)
- `F` = force vector (ship frame)

### Example: Yaw Control

To yaw the ship (rotate around Z), thrusters at the bow push port/starboard:

```yaml
thrusters:
  - id: "bow_port"
    position: [10.0, -5.0, 0.0]   # Forward, port side
    direction: [0.0, 1.0, 0.0]    # Pushes starboard
    max_thrust: 1000.0
```

This creates positive Z torque (yaw left).

## Coordinate Frame Transformations

### Ship Frame to World Frame

To convert a vector from ship frame to world frame:

```python
world_vec = ship.quaternion.rotate_vector(ship_frame_vec)
```

### World Frame to Ship Frame

To convert a vector from world frame to ship frame:

```python
ship_frame_vec = ship.quaternion.conjugate().rotate_vector(world_vec)
```

## GUI Conventions

### Throttle Control

- Sends scalar `thrust` value (0.0 to 1.0)
- Server applies thrust along ship's +X axis in body frame
- Rotation to world frame handled by quaternion

### Heading Control

- Sends target attitude as Euler angles (pitch, yaw, roll)
- Server sets this as RCS attitude target
- RCS maneuvers ship to achieve target (not instantaneous)

### Tactical Map

- 2D overhead view (X-Y plane, Z is into screen)
- North = +Y, East = +X
- Ship markers show heading via rotation

## Common Pitfalls

1. **Don't assume axes**: Always check which axis is "forward" - it's +X in this sim.

2. **Euler angle singularities**: Pitch near ±90° can cause numerical issues; the quaternion representation handles this automatically.

3. **Thrust direction**: Main drive thrust acts along +X (forward), not Z. Exhaust points -X (aft).

4. **RCS translation**: RCS is for attitude control only in the current implementation - no translation jets.

5. **World vs ship frame**: Velocities and positions are in world frame; thrust vectors start in ship frame and are rotated.

## References

- `hybrid/utils/quaternion.py` - Quaternion implementation
- `hybrid/systems/propulsion_system.py` - Main drive thrust
- `hybrid/systems/rcs_system.py` - RCS attitude control
- `docs/RCS_CONFIGURATION_GUIDE.md` - Thruster configuration format
