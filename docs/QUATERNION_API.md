# Quaternion API Reference

**Status**: ✅ Implemented
**Sprint**: S3 (Quaternion Attitude Foundation)
**Last Updated**: 2026-01-25

---

## Overview

The quaternion module provides a complete rotation math API used by the
attitude system to eliminate gimbal lock and support smooth interpolation.
All public methods use **degrees** for angle inputs/outputs unless noted.

**Location**: `hybrid/utils/quaternion.py`

---

## Coordinate & Rotation Conventions

- **Euler order**: ZYX intrinsic rotations (yaw → pitch → roll).
- **Angles**: Degrees in public API.
- **Vector rotation**: Uses `q * v * q⁻¹`.
- **Unit quaternions** represent pure rotations (no scaling).

---

## Class: `Quaternion`

### Constructor
```python
Quaternion(w=1.0, x=0.0, y=0.0, z=0.0)
```
Creates a quaternion from raw components. Defaults to the identity rotation.

### Factory Methods
```python
Quaternion.from_euler(pitch, yaw, roll)
```
Creates a quaternion from Euler angles (degrees, ZYX intrinsic order).

```python
Quaternion.from_axis_angle(axis, angle)
```
Creates a quaternion from an axis vector and a rotation angle in degrees.
Axis inputs are normalized automatically.

### Conversion Methods
```python
Quaternion.to_euler()
```
Returns `(pitch, yaw, roll)` in degrees.

```python
Quaternion.to_axis_angle()
```
Returns `(axis, angle)` where axis is a normalized numpy vector and
angle is in degrees.

```python
Quaternion.to_rotation_matrix()
```
Returns a `3x3` numpy rotation matrix.

### Core Operations
```python
Quaternion.normalize()
```
Normalizes the quaternion in place.

```python
Quaternion.normalized()
```
Returns a normalized copy.

```python
Quaternion.conjugate()
```
Returns the conjugate (inverse for unit quaternions).

```python
Quaternion.inverse()
```
Returns the inverse (conjugate / ||q||²).

```python
Quaternion.__mul__(other)
```
Quaternion multiplication (rotation composition).

```python
Quaternion.rotate_vector(vector)
```
Rotates a vector (x, y, z) using `q * v * q⁻¹`.

### Interpolation
```python
Quaternion.slerp(q1, q2, t)
```
Spherical linear interpolation from `q1` to `q2` with `t ∈ [0, 1]`.

### Utility
```python
Quaternion.magnitude()
Quaternion.is_unit(epsilon=1e-6)
Quaternion.dot(other)
```
Magnitude, unit check, and dot product helpers.

---

## Module Helpers

```python
quaternion_identity()
```
Returns the identity quaternion `(1, 0, 0, 0)`.

```python
quaternion_from_to(from_vec, to_vec)
```
Creates a quaternion that rotates one vector to align with another.

---

## Usage Examples

### Convert Euler → Quaternion → Euler
```python
from hybrid.utils.quaternion import Quaternion

q = Quaternion.from_euler(10, 20, 30)
pitch, yaw, roll = q.to_euler()
```

### Rotate a Vector
```python
from hybrid.utils.quaternion import Quaternion

q = Quaternion.from_axis_angle([0, 0, 1], 90)  # 90° yaw
forward = [1, 0, 0]
left = q.rotate_vector(forward)
```

### Smoothly Interpolate Orientation
```python
from hybrid.utils.quaternion import Quaternion

q_start = Quaternion.from_euler(0, 0, 0)
q_end = Quaternion.from_euler(0, 90, 0)
q_mid = Quaternion.slerp(q_start, q_end, 0.5)
```

---

## Tests

- `tests/utils/test_quaternion.py` exercises creation, conversions,
  multiplication, SLERP, and vector rotation.

