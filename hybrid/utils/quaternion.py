"""
Quaternion mathematics for 3D rotations.

Solves gimbal lock issues by representing rotations as quaternions instead
of Euler angles. Provides conversion between representations and all standard
quaternion operations.

Convention:
- Quaternion stored as (w, x, y, z) where w is scalar, (x, y, z) is vector
- Euler angles in degrees unless specified
- Rotation order: Z-Y-X (yaw-pitch-roll)
- Right-handed coordinate system
"""

import math
from typing import Tuple, Optional


class Quaternion:
    """
    Quaternion for representing 3D rotations.

    Quaternions avoid gimbal lock and provide smooth interpolation
    for rotations. This class provides conversion to/from Euler angles
    for backward compatibility.

    Attributes:
        w: Scalar component
        x, y, z: Vector components
    """

    def __init__(self, w: float = 1.0, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        """
        Initialize quaternion.

        Args:
            w: Scalar component (default: 1.0 for identity)
            x: X vector component
            y: Y vector component
            z: Z vector component
        """
        self.w = w
        self.x = x
        self.y = y
        self.z = z

    @classmethod
    def from_euler(cls, pitch: float, yaw: float, roll: float, degrees: bool = True) -> 'Quaternion':
        """
        Create quaternion from Euler angles.

        Rotation order: Z-Y-X (yaw-pitch-roll)

        Args:
            pitch: Rotation around Y axis (nose up/down)
            yaw: Rotation around Z axis (nose left/right)
            roll: Rotation around X axis (rotation around forward)
            degrees: If True, angles are in degrees (default: True)

        Returns:
            Quaternion representing the rotation

        Example:
            >>> q = Quaternion.from_euler(15.0, 45.0, 0.0)  # 15° pitch, 45° yaw
        """
        if degrees:
            pitch = math.radians(pitch)
            yaw = math.radians(yaw)
            roll = math.radians(roll)

        # Calculate half angles
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)

        # Quaternion multiplication: Z * Y * X
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy

        return cls(w, x, y, z)

    def to_euler(self, degrees: bool = True) -> Tuple[float, float, float]:
        """
        Convert quaternion to Euler angles.

        Returns angles in rotation order: Z-Y-X (yaw-pitch-roll)

        Args:
            degrees: If True, return angles in degrees (default: True)

        Returns:
            Tuple of (pitch, yaw, roll) in degrees or radians

        Example:
            >>> q = Quaternion.from_euler(15.0, 45.0, 0.0)
            >>> pitch, yaw, roll = q.to_euler()
        """
        # Roll (x-axis rotation)
        sinr_cosp = 2.0 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1.0 - 2.0 * (self.x * self.x + self.y * self.y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # Pitch (y-axis rotation)
        sinp = 2.0 * (self.w * self.y - self.z * self.x)
        if abs(sinp) >= 1.0:
            # Gimbal lock case: use 90 degrees if out of range
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        # Yaw (z-axis rotation)
        siny_cosp = 2.0 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1.0 - 2.0 * (self.y * self.y + self.z * self.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        if degrees:
            pitch = math.degrees(pitch)
            yaw = math.degrees(yaw)
            roll = math.degrees(roll)

        return (pitch, yaw, roll)

    def normalize(self) -> 'Quaternion':
        """
        Return normalized quaternion (unit quaternion).

        Unit quaternions represent valid rotations. This should be called
        after arithmetic operations to maintain numerical stability.

        Returns:
            Normalized copy of this quaternion

        Example:
            >>> q = Quaternion(1.0, 1.0, 1.0, 1.0)
            >>> q_norm = q.normalize()
            >>> assert abs(q_norm.magnitude() - 1.0) < 1e-9
        """
        mag = self.magnitude()
        if mag < 1e-10:
            # Degenerate quaternion, return identity
            return Quaternion(1.0, 0.0, 0.0, 0.0)

        return Quaternion(
            self.w / mag,
            self.x / mag,
            self.y / mag,
            self.z / mag
        )

    def magnitude(self) -> float:
        """
        Calculate magnitude (length) of quaternion.

        Returns:
            Magnitude of quaternion
        """
        return math.sqrt(self.w * self.w + self.x * self.x +
                        self.y * self.y + self.z * self.z)

    def conjugate(self) -> 'Quaternion':
        """
        Return conjugate of quaternion.

        The conjugate is (w, -x, -y, -z). For unit quaternions,
        the conjugate equals the inverse.

        Returns:
            Conjugate quaternion
        """
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def inverse(self) -> 'Quaternion':
        """
        Return inverse of quaternion.

        For unit quaternions, inverse equals conjugate.
        For non-unit quaternions, inverse = conjugate / magnitude²

        Returns:
            Inverse quaternion
        """
        mag_sq = (self.w * self.w + self.x * self.x +
                  self.y * self.y + self.z * self.z)

        if mag_sq < 1e-10:
            # Degenerate quaternion, return identity
            return Quaternion(1.0, 0.0, 0.0, 0.0)

        conj = self.conjugate()
        return Quaternion(
            conj.w / mag_sq,
            conj.x / mag_sq,
            conj.y / mag_sq,
            conj.z / mag_sq
        )

    def __mul__(self, other: 'Quaternion') -> 'Quaternion':
        """
        Multiply two quaternions (compose rotations).

        Quaternion multiplication is non-commutative: q1 * q2 != q2 * q1
        The result represents applying q2 rotation, then q1 rotation.

        Args:
            other: Quaternion to multiply with

        Returns:
            Product quaternion

        Example:
            >>> q1 = Quaternion.from_euler(10, 0, 0)  # 10° pitch
            >>> q2 = Quaternion.from_euler(0, 20, 0)  # 20° yaw
            >>> q_combined = q1 * q2  # Apply yaw, then pitch
        """
        w = self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z
        x = self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y
        y = self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x
        z = self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w

        return Quaternion(w, x, y, z)

    def rotate_vector(self, v: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Rotate a 3D vector by this quaternion.

        Uses the formula: v' = q * v * q⁻¹
        where v is treated as a pure quaternion (0, x, y, z)

        Args:
            v: 3D vector as (x, y, z) tuple

        Returns:
            Rotated vector as (x, y, z) tuple

        Example:
            >>> q = Quaternion.from_euler(0, 90, 0)  # 90° yaw
            >>> v_rotated = q.rotate_vector((1.0, 0.0, 0.0))
            >>> # Should rotate X-axis vector to point along Y-axis
        """
        # Convert vector to pure quaternion
        v_quat = Quaternion(0.0, v[0], v[1], v[2])

        # Perform rotation: q * v * q⁻¹
        result = self * v_quat * self.conjugate()

        return (result.x, result.y, result.z)

    @staticmethod
    def slerp(q1: 'Quaternion', q2: 'Quaternion', t: float) -> 'Quaternion':
        """
        Spherical linear interpolation between two quaternions.

        SLERP provides smooth interpolation between rotations at constant
        angular velocity. Essential for animation and autopilot systems.

        Args:
            q1: Start quaternion (t=0)
            q2: End quaternion (t=1)
            t: Interpolation parameter [0, 1]

        Returns:
            Interpolated quaternion

        Example:
            >>> q_start = Quaternion.from_euler(0, 0, 0)
            >>> q_end = Quaternion.from_euler(90, 0, 0)
            >>> q_mid = Quaternion.slerp(q_start, q_end, 0.5)  # 45° pitch
        """
        # Clamp t to [0, 1]
        t = max(0.0, min(1.0, t))

        # Compute dot product
        dot = q1.w * q2.w + q1.x * q2.x + q1.y * q2.y + q1.z * q2.z

        # If quaternions are close, use linear interpolation
        if abs(dot) > 0.9995:
            # Linear interpolation
            w = q1.w + t * (q2.w - q1.w)
            x = q1.x + t * (q2.x - q1.x)
            y = q1.y + t * (q2.y - q1.y)
            z = q1.z + t * (q2.z - q1.z)
            return Quaternion(w, x, y, z).normalize()

        # If dot product is negative, negate q2 to take shorter path
        if dot < 0.0:
            q2 = Quaternion(-q2.w, -q2.x, -q2.y, -q2.z)
            dot = -dot

        # Clamp dot product to avoid numerical errors with acos
        dot = max(-1.0, min(1.0, dot))

        # Calculate angle between quaternions
        theta = math.acos(dot)
        sin_theta = math.sin(theta)

        if abs(sin_theta) < 1e-10:
            # Quaternions are very close, use linear interpolation
            w = q1.w + t * (q2.w - q1.w)
            x = q1.x + t * (q2.x - q1.x)
            y = q1.y + t * (q2.y - q1.y)
            z = q1.z + t * (q2.z - q1.z)
            return Quaternion(w, x, y, z).normalize()

        # Spherical interpolation
        scale1 = math.sin((1.0 - t) * theta) / sin_theta
        scale2 = math.sin(t * theta) / sin_theta

        w = scale1 * q1.w + scale2 * q2.w
        x = scale1 * q1.x + scale2 * q2.x
        y = scale1 * q1.y + scale2 * q2.y
        z = scale1 * q1.z + scale2 * q2.z

        return Quaternion(w, x, y, z)

    def dot(self, other: 'Quaternion') -> float:
        """
        Calculate dot product with another quaternion.

        The dot product indicates how similar two rotations are.
        Value of 1.0 means identical rotations, -1.0 means opposite.

        Args:
            other: Other quaternion

        Returns:
            Dot product
        """
        return self.w * other.w + self.x * other.x + self.y * other.y + self.z * other.z

    def __repr__(self) -> str:
        """String representation of quaternion."""
        return f"Quaternion(w={self.w:.6f}, x={self.x:.6f}, y={self.y:.6f}, z={self.z:.6f})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"Quat[w={self.w:.3f}, x={self.x:.3f}, y={self.y:.3f}, z={self.z:.3f}]"

    def __eq__(self, other: 'Quaternion') -> bool:
        """Check equality with tolerance for floating point errors."""
        if not isinstance(other, Quaternion):
            return False

        epsilon = 1e-9
        return (abs(self.w - other.w) < epsilon and
                abs(self.x - other.x) < epsilon and
                abs(self.y - other.y) < epsilon and
                abs(self.z - other.z) < epsilon)

    def copy(self) -> 'Quaternion':
        """Create a copy of this quaternion."""
        return Quaternion(self.w, self.x, self.y, self.z)

    @staticmethod
    def identity() -> 'Quaternion':
        """
        Create identity quaternion (no rotation).

        Returns:
            Identity quaternion (1, 0, 0, 0)
        """
        return Quaternion(1.0, 0.0, 0.0, 0.0)

    @classmethod
    def from_axis_angle(cls, axis: Tuple[float, float, float], angle: float,
                        degrees: bool = True) -> 'Quaternion':
        """
        Create quaternion from axis-angle representation.

        Args:
            axis: Rotation axis as (x, y, z) tuple (will be normalized)
            angle: Rotation angle around axis
            degrees: If True, angle is in degrees (default: True)

        Returns:
            Quaternion representing the rotation

        Example:
            >>> q = Quaternion.from_axis_angle((0, 1, 0), 90)  # 90° around Y
        """
        if degrees:
            angle = math.radians(angle)

        # Normalize axis
        ax, ay, az = axis
        axis_len = math.sqrt(ax*ax + ay*ay + az*az)

        if axis_len < 1e-10:
            # Zero axis, return identity
            return cls.identity()

        ax /= axis_len
        ay /= axis_len
        az /= axis_len

        # Calculate quaternion
        half_angle = angle * 0.5
        s = math.sin(half_angle)

        return cls(
            math.cos(half_angle),
            ax * s,
            ay * s,
            az * s
        )

    def to_axis_angle(self, degrees: bool = True) -> Tuple[Tuple[float, float, float], float]:
        """
        Convert quaternion to axis-angle representation.

        Args:
            degrees: If True, return angle in degrees (default: True)

        Returns:
            Tuple of (axis, angle) where axis is (x, y, z)

        Example:
            >>> q = Quaternion.from_euler(0, 90, 0)
            >>> axis, angle = q.to_axis_angle()
        """
        # Normalize quaternion
        q = self.normalize()

        # Calculate angle
        angle = 2.0 * math.acos(max(-1.0, min(1.0, q.w)))

        # Calculate axis
        sin_half_angle = math.sqrt(1.0 - q.w * q.w)

        if sin_half_angle < 1e-10:
            # Angle is 0 or 360, axis doesn't matter
            axis = (1.0, 0.0, 0.0)
        else:
            axis = (q.x / sin_half_angle,
                   q.y / sin_half_angle,
                   q.z / sin_half_angle)

        if degrees:
            angle = math.degrees(angle)

        return (axis, angle)


# Utility functions

def integrate_angular_velocity(q: Quaternion, angular_velocity: Tuple[float, float, float],
                               dt: float) -> Quaternion:
    """
    Integrate angular velocity to update quaternion orientation.

    Uses first-order integration for simplicity and performance.
    More accurate than Euler angle integration, especially near gimbal lock.

    Args:
        q: Current orientation quaternion
        angular_velocity: Angular velocity as (wx, wy, wz) in rad/s
        dt: Time step in seconds

    Returns:
        Updated quaternion after dt seconds

    Example:
        >>> q = Quaternion.identity()
        >>> # 10 degrees/second pitch rate
        >>> w = (0, math.radians(10), 0)
        >>> q_new = integrate_angular_velocity(q, w, 0.1)  # 1 degree change
    """
    wx, wy, wz = angular_velocity

    # Create rate quaternion
    dq = Quaternion(
        0.0,
        wx * dt * 0.5,
        wy * dt * 0.5,
        wz * dt * 0.5
    )

    # Integrate: q_new = q + dq * q
    q_new = Quaternion(
        q.w + (-dq.x * q.x - dq.y * q.y - dq.z * q.z),
        q.x + (dq.x * q.w + dq.y * q.z - dq.z * q.y),
        q.y + (dq.y * q.w - dq.x * q.z + dq.z * q.x),
        q.z + (dq.z * q.w + dq.x * q.y - dq.y * q.x)
    )

    # Normalize to prevent drift
    return q_new.normalize()


def quaternion_between_vectors(v1: Tuple[float, float, float],
                               v2: Tuple[float, float, float]) -> Quaternion:
    """
    Calculate quaternion that rotates v1 to align with v2.

    Useful for calculating bearing to target in 3D space.

    Args:
        v1: Start vector (will be normalized)
        v2: End vector (will be normalized)

    Returns:
        Quaternion rotating v1 to v2

    Example:
        >>> # Calculate rotation from forward (1,0,0) to target direction
        >>> q = quaternion_between_vectors((1, 0, 0), (0, 1, 0))
    """
    # Normalize vectors
    v1_len = math.sqrt(v1[0]*v1[0] + v1[1]*v1[1] + v1[2]*v1[2])
    v2_len = math.sqrt(v2[0]*v2[0] + v2[1]*v2[1] + v2[2]*v2[2])

    if v1_len < 1e-10 or v2_len < 1e-10:
        return Quaternion.identity()

    v1_norm = (v1[0]/v1_len, v1[1]/v1_len, v1[2]/v1_len)
    v2_norm = (v2[0]/v2_len, v2[1]/v2_len, v2[2]/v2_len)

    # Calculate dot product
    dot = v1_norm[0]*v2_norm[0] + v1_norm[1]*v2_norm[1] + v1_norm[2]*v2_norm[2]

    # Check if vectors are parallel
    if dot > 0.9999:
        # Same direction, return identity
        return Quaternion.identity()

    if dot < -0.9999:
        # Opposite directions, rotate 180° around any perpendicular axis
        # Find perpendicular axis
        if abs(v1_norm[0]) < 0.9:
            axis = (1.0, 0.0, 0.0)
        else:
            axis = (0.0, 1.0, 0.0)

        # Cross product to get perpendicular
        cross = (
            v1_norm[1] * axis[2] - v1_norm[2] * axis[1],
            v1_norm[2] * axis[0] - v1_norm[0] * axis[2],
            v1_norm[0] * axis[1] - v1_norm[1] * axis[0]
        )

        return Quaternion.from_axis_angle(cross, 180.0)

    # Normal case: calculate rotation axis via cross product
    cross = (
        v1_norm[1] * v2_norm[2] - v1_norm[2] * v2_norm[1],
        v1_norm[2] * v2_norm[0] - v1_norm[0] * v2_norm[2],
        v1_norm[0] * v2_norm[1] - v1_norm[1] * v2_norm[0]
    )

    # Quaternion components
    w = math.sqrt((v1_len * v2_len)**2) + dot

    return Quaternion(w, cross[0], cross[1], cross[2]).normalize()
