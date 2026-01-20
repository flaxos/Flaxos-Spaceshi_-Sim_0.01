# RCS Configuration Guide

**Last Updated**: 2026-01-26
**Sprint**: S3 (Quaternion Attitude)

---

## Overview

This guide documents the Reaction Control System (RCS) configuration format used by ship YAML definitions in `hybrid_fleet/ship_configs/`. The RCS system defines thruster placement, thrust vectors, and fuel consumption so the simulator can compute torque from each nozzle and apply it to the ship’s attitude controller.

RCS configurations are **data-only**: they describe the ship’s thruster hardware and do not encode control logic. Control logic lives in the RCS system implementation and autopilot logic.

---

## Where RCS Configurations Live

Place RCS definitions in a ship’s YAML configuration under the `systems.rcs` key. Example file locations include:

- `hybrid_fleet/ship_configs/frigate.yaml`
- `hybrid_fleet/ship_configs/corvette.yaml`

The ship factory will read these configurations when the RCS system is implemented and registered in `hybrid/ship_factory.py`.

---

## YAML Structure

```yaml
systems:
  rcs:
    enabled: true
    fuel_type: "rcs_propellant"
    thrusters:
      - id: "bow_port"
        position: [10.0, -5.0, 0.0]   # meters from center of mass
        direction: [0.0, 1.0, 0.0]    # unit vector for thrust direction
        max_thrust: 1000.0            # Newtons
        fuel_consumption: 0.1         # kg/s at max thrust
```

### Top-Level Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `enabled` | bool | Yes | Enables or disables the RCS system at startup. |
| `fuel_type` | string | Yes | Fuel resource key used by the ship’s resource system. |
| `thrusters` | list | Yes | Array of thruster definitions (see below). |

### Thruster Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | Yes | Unique ID for telemetry and debugging. |
| `position` | list[float, float, float] | Yes | Position in meters relative to ship center of mass. |
| `direction` | list[float, float, float] | Yes | **Unit vector** for thrust direction. |
| `max_thrust` | float | Yes | Maximum thrust output in Newtons. |
| `fuel_consumption` | float | Yes | Fuel usage in kg/s at full thrust. |

---

## Example Configuration (Frigate)

```yaml
systems:
  rcs:
    enabled: true
    fuel_type: "rcs_propellant"
    thrusters:
      # Bow thrusters (yaw control)
      - id: "bow_port"
        position: [10.0, -5.0, 0.0]
        direction: [0.0, 1.0, 0.0]
        max_thrust: 1000.0
        fuel_consumption: 0.1

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

---

## Configuration Notes & Best Practices

1. **Use consistent coordinate frames.** Positions are measured in meters from the ship’s center of mass using the same axes as ship physics.
2. **Normalize direction vectors.** Direction should be a unit vector; the RCS system will scale it by `max_thrust`.
3. **Balance opposing thrusters.** Pairing thrusters on opposite sides of the hull improves control authority and reduces unintended translation.
4. **Keep IDs stable.** Telemetry and debugging rely on the `id` field.
5. **Avoid hardcoding bus/system names.** RCS system registration should reference schema keys defined in `systems_schema.py`.

---

## Validation Checklist

Before shipping a new RCS configuration:

- [ ] Positions are relative to center of mass.
- [ ] Direction vectors are normalized.
- [ ] `max_thrust` values match ship class scale.
- [ ] Fuel consumption values align with ship propellant capacity.
- [ ] Thruster IDs are unique across the ship.

---

## Next Steps

- Implement `hybrid/systems/rcs_system.py` and register it in `hybrid/ship_factory.py`.
- Add unit tests in `tests/systems/test_rcs_system.py` to validate config parsing and torque calculations.
- Create or update ship configurations in `hybrid_fleet/ship_configs/`.
