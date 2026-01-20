"""
Quaternion mathematics for 3D rotations.

Quaternions eliminate gimbal lock and provide smooth interpolation for rotations.
This module provides a complete quaternion implementation for spacecraft attitude control.

References:
- https://en.wikipedia.org/wiki/Quaternion
- https://en.wikipedia.org/wiki/Conversion_between_quaternions_and_Euler_angles
"""

import math
import numpy as np
from typing import Tuple, Union


class Quaternion:
    """
    Quaternion for representing 3D rotations.

    A quaternion is a 4-component number (w, x, y, z) that represents a rotation.
    Unit quaternions (||q|| = 1) represent rotations without scaling.

    Attributes:
        w (float): Scalar component (real part)
        x (float): i component (imaginary)
        y (float): j component (imaginary)
        z (float): k component (imaginary)
    """

    def __init__(self, w: float = 1.0, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        """
        Create a quaternion from components.

        Args:
            w: Scalar (real) component, defaults to 1.0 (identity)
            x: i component, defaults to 0.0
            y: j component, defaults to 0.0
            z: k component, defaults to 0.0
        """
        self.w = float(w)
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)

    @classmethod
    def from_euler(cls, pitch: float, yaw: float, roll: float) -> 'Quaternion':
        """
        Create quaternion from Euler angles (intrinsic rotations, ZYX order).

        Args:
            pitch: Rotation around Y axis (degrees), nose up/down
            yaw: Rotation around Z axis (degrees), nose left/right
            roll: Rotation around X axis (degrees), barrel roll

        Returns:
            Quaternion representing the rotation

        Note:
            Uses aerospace convention (ZYX intrinsic rotations):
            1. First rotate yaw around Z axis
            2. Then rotate pitch around Y axis
            3. Finally rotate roll around X axis
        """
        # Convert degrees to radians
        pitch_rad = math.radians(pitch)
        yaw_rad = math.radians(yaw)
        roll_rad = math.radians(roll)

        # Half angles
        cy = math.cos(yaw_rad * 0.5)
        sy = math.sin(yaw_rad * 0.5)
        cp = math.cos(pitch_rad * 0.5)
        sp = math.sin(pitch_rad * 0.5)
        cr = math.cos(roll_rad * 0.5)
        sr = math.sin(roll_rad * 0.5)

        # Quaternion multiplication: yaw * pitch * roll
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy

        return cls(w, x, y, z)

    @classmethod
    def from_axis_angle(cls, axis: Union[np.ndarray, Tuple[float, float, float]],
                       angle: float) -> 'Quaternion':
        """
        Create quaternion from axis-angle representation.

        Args:
            axis: Rotation axis as (x, y, z) - will be normalized
            angle: Rotation angle in degrees

        Returns:
            Quaternion representing the rotation
        """
        # Normalize axis
        axis = np.array(axis, dtype=float)
        magnitude = np.linalg.norm(axis)

        if magnitude < 1e-10:
            # No rotation (zero axis)
            return cls(1.0, 0.0, 0.0, 0.0)

        axis = axis / magnitude

        # Convert to quaternion
        angle_rad = math.radians(angle)
        half_angle = angle_rad * 0.5
        s = math.sin(half_angle)

        w = math.cos(half_angle)
        x = axis[0] * s
        y = axis[1] * s
        z = axis[2] * s

        return cls(w, x, y, z)

    def to_euler(self) -> Tuple[float, float, float]:
        """
        Convert quaternion to Euler angles (ZYX intrinsic rotations).

        Returns:
            Tuple of (pitch, yaw, roll) in degrees

        Note:
            This conversion can have ambiguities near gimbal lock positions.
            The quaternion representation itself does not have this issue.
        """
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (self.w * self.x + self.y * self.z)
        cosr_cosp = 1 - 2 * (self.x * self.x + self.y * self.y)
        roll = math.degrees(math.atan2(sinr_cosp, cosr_cosp))

        # Pitch (y-axis rotation)
        sinp = 2 * (self.w * self.y - self.z * self.x)
        if abs(sinp) >= 1:
            # Gimbal lock case
            pitch = math.degrees(math.copysign(math.pi / 2, sinp))
        else:
            pitch = math.degrees(math.asin(sinp))

        # Yaw (z-axis rotation)
        siny_cosp = 2 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1 - 2 * (self.y * self.y + self.z * self.z)
        yaw = math.degrees(math.atan2(siny_cosp, cosy_cosp))

        return (pitch, yaw, roll)

    def to_axis_angle(self) -> Tuple[np.ndarray, float]:
        """
        Convert quaternion to axis-angle representation.

        Returns:
            Tuple of (axis, angle) where axis is normalized (x,y,z) and angle is in degrees
        """
        # Normalize first
        q = self.normalized()

        # Handle identity quaternion
        if abs(q.w) >= 1.0:
            return (np.array([1.0, 0.0, 0.0]), 0.0)

        angle = 2 * math.acos(q.w)
        s = math.sqrt(1 - q.w * q.w)

        if s < 1e-10:
            # Angle very small, axis doesn't matter
            axis = np.array([1.0, 0.0, 0.0])
        else:
            axis = np.array([q.x / s, q.y / s, q.z / s])

        return (axis, math.degrees(angle))

    def normalize(self) -> None:
        """
        Normalize this quaternion to unit length (in-place).

        Unit quaternions represent pure rotations without scaling.
        """
        magnitude = math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)

        if magnitude < 1e-10:
            # Degenerate case - reset to identity
            self.w = 1.0
            self.x = 0.0
            self.y = 0.0
            self.z = 0.0
        else:
            self.w /= magnitude
            self.x /= magnitude
            self.y /= magnitude
            self.z /= magnitude

    def normalized(self) -> 'Quaternion':
        """
        Return a normalized copy of this quaternion.

        Returns:
            New quaternion with unit length
        """
        magnitude = math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)

        if magnitude < 1e-10:
            return Quaternion(1.0, 0.0, 0.0, 0.0)

        return Quaternion(
            self.w / magnitude,
            self.x / magnitude,
            self.y / magnitude,
            self.z / magnitude
        )

    def conjugate(self) -> 'Quaternion':
        """
        Return the conjugate of this quaternion.

        For unit quaternions, the conjugate is the inverse rotation.

        Returns:
            Conjugate quaternion (w, -x, -y, -z)
        """
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def inverse(self) -> 'Quaternion':
        """
        Return the inverse of this quaternion.

        For unit quaternions, inverse = conjugate.
        For non-unit quaternions, inverse = conjugate / ||q||^2

        Returns:
            Inverse quaternion
        """
        norm_squared = self.w**2 + self.x**2 + self.y**2 + self.z**2

        if norm_squared < 1e-10:
            # Degenerate case
            return Quaternion(1.0, 0.0, 0.0, 0.0)

        conj = self.conjugate()
        return Quaternion(
            conj.w / norm_squared,
            conj.x / norm_squared,
            conj.y / norm_squared,
            conj.z / norm_squared
        )

    def __mul__(self, other: 'Quaternion') -> 'Quaternion':
        """
        Multiply this quaternion by another (quaternion composition).

        This represents composing rotations: q1 * q2 means "first apply q2, then q1"

        Args:
            other: Quaternion to multiply with

        Returns:
            Product quaternion
        """
        w = self.w * other.w - self.x * other.x - self.y * other.y - self.z * other.z
        x = self.w * other.x + self.x * other.w + self.y * other.z - self.z * other.y
        y = self.w * other.y - self.x * other.z + self.y * other.w + self.z * other.x
        z = self.w * other.z + self.x * other.y - self.y * other.x + self.z * other.w

        return Quaternion(w, x, y, z)

    def __add__(self, other: 'Quaternion') -> 'Quaternion':
        """
        Add two quaternions component-wise.

        Note: This is used for quaternion integration, not rotation composition.

        Args:
            other: Quaternion to add

        Returns:
            Sum quaternion
        """
        return Quaternion(
            self.w + other.w,
            self.x + other.x,
            self.y + other.y,
            self.z + other.z
        )

    def __sub__(self, other: 'Quaternion') -> 'Quaternion':
        """
        Subtract two quaternions component-wise.

        Args:
            other: Quaternion to subtract

        Returns:
            Difference quaternion
        """
        return Quaternion(
            self.w - other.w,
            self.x - other.x,
            self.y - other.y,
            self.z - other.z
        )

    def __rmul__(self, scalar: float) -> 'Quaternion':
        """
        Multiply quaternion by scalar (scalar * quaternion).

        Args:
            scalar: Scalar value

        Returns:
            Scaled quaternion
        """
        return Quaternion(
            scalar * self.w,
            scalar * self.x,
            scalar * self.y,
            scalar * self.z
        )

    def scale(self, scalar: float) -> 'Quaternion':
        """
        Multiply quaternion by scalar (quaternion * scalar).

        Args:
            scalar: Scalar value

        Returns:
            Scaled quaternion
        """
        return Quaternion(
            self.w * scalar,
            self.x * scalar,
            self.y * scalar,
            self.z * scalar
        )

    def rotate_vector(self, vector: Union[np.ndarray, Tuple[float, float, float]]) -> np.ndarray:
        """
        Rotate a 3D vector by this quaternion.

        Uses the formula: v' = q * v * q^(-1)
        where v is represented as a pure quaternion (0, v.x, v.y, v.z)

        Args:
            vector: Vector to rotate as (x, y, z)

        Returns:
            Rotated vector as numpy array
        """
        v = np.array(vector, dtype=float)

        # Represent vector as pure quaternion
        v_quat = Quaternion(0, v[0], v[1], v[2])

        # Rotate: q * v * q^(-1)
        result = self * v_quat * self.conjugate()

        return np.array([result.x, result.y, result.z])

    def dot(self, other: 'Quaternion') -> float:
        """
        Compute dot product with another quaternion.

        Args:
            other: Other quaternion

        Returns:
            Dot product (scalar)
        """
        return self.w * other.w + self.x * other.x + self.y * other.y + self.z * other.z

    @staticmethod
    def slerp(q1: 'Quaternion', q2: 'Quaternion', t: float) -> 'Quaternion':
        """
        Spherical linear interpolation between two quaternions.

        Provides smooth interpolation between rotations, maintaining constant angular velocity.

        Args:
            q1: Start quaternion
            q2: End quaternion
            t: Interpolation parameter [0, 1], where 0 = q1, 1 = q2

        Returns:
            Interpolated quaternion
        """
        # Clamp t to [0, 1]
        t = max(0.0, min(1.0, t))

        # Normalize inputs
        q1_norm = q1.normalized()
        q2_norm = q2.normalized()

        # Compute dot product
        dot = q1_norm.dot(q2_norm)

        # If dot product is negative, negate q2 to take shorter path
        if dot < 0.0:
            q2_norm = Quaternion(-q2_norm.w, -q2_norm.x, -q2_norm.y, -q2_norm.z)
            dot = -dot

        # If quaternions are very close, use linear interpolation
        if dot > 0.9995:
            # Linear interpolation
            result = Quaternion(
                q1_norm.w + t * (q2_norm.w - q1_norm.w),
                q1_norm.x + t * (q2_norm.x - q1_norm.x),
                q1_norm.y + t * (q2_norm.y - q1_norm.y),
                q1_norm.z + t * (q2_norm.z - q1_norm.z)
            )
            result.normalize()
            return result

        # Spherical interpolation
        theta = math.acos(dot)
        sin_theta = math.sin(theta)

        w1 = math.sin((1 - t) * theta) / sin_theta
        w2 = math.sin(t * theta) / sin_theta

        return Quaternion(
            w1 * q1_norm.w + w2 * q2_norm.w,
            w1 * q1_norm.x + w2 * q2_norm.x,
            w1 * q1_norm.y + w2 * q2_norm.y,
            w1 * q1_norm.z + w2 * q2_norm.z
        )

    def to_rotation_matrix(self) -> np.ndarray:
        """
        Convert quaternion to 3x3 rotation matrix.

        Returns:
            3x3 numpy array representing the rotation matrix
        """
        # Normalize first
        q = self.normalized()

        w, x, y, z = q.w, q.x, q.y, q.z

        return np.array([
            [1 - 2*(y*y + z*z),     2*(x*y - w*z),     2*(x*z + w*y)],
            [    2*(x*y + w*z), 1 - 2*(x*x + z*z),     2*(y*z - w*x)],
            [    2*(x*z - w*y),     2*(y*z + w*x), 1 - 2*(x*x + y*y)]
        ])

    def magnitude(self) -> float:
        """
        Compute the magnitude (norm) of this quaternion.

        Returns:
            Magnitude ||q||
        """
        return math.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)

    def __repr__(self) -> str:
        """String representation of quaternion."""
        return f"Quaternion(w={self.w:.4f}, x={self.x:.4f}, y={self.y:.4f}, z={self.z:.4f})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"Quat({self.w:.4f}, {self.x:.4f}, {self.y:.4f}, {self.z:.4f})"

    def __eq__(self, other: 'Quaternion') -> bool:
        """
        Check equality with another quaternion.

        Note: q and -q represent the same rotation, but this checks component equality.
        """
        if not isinstance(other, Quaternion):
            return False

        epsilon = 1e-6
        return (abs(self.w - other.w) < epsilon and
                abs(self.x - other.x) < epsilon and
                abs(self.y - other.y) < epsilon and
                abs(self.z - other.z) < epsilon)

    def is_unit(self, epsilon: float = 1e-6) -> bool:
        """
        Check if this is a unit quaternion (within tolerance).

        Args:
            epsilon: Tolerance for unit test

        Returns:
            True if magnitude is approximately 1
        """
        mag = self.magnitude()
        return abs(mag - 1.0) < epsilon


# Convenience functions
def quaternion_identity() -> Quaternion:
    """
    Create an identity quaternion (no rotation).

    Returns:
        Identity quaternion (1, 0, 0, 0)
    """
    return Quaternion(1.0, 0.0, 0.0, 0.0)


def quaternion_from_to(from_vec: np.ndarray, to_vec: np.ndarray) -> Quaternion:
    """
    Create a quaternion that rotates from_vec to align with to_vec.

    Args:
        from_vec: Starting vector
        to_vec: Target vector

    Returns:
        Quaternion representing the rotation
    """
    from_vec = np.array(from_vec, dtype=float)
    to_vec = np.array(to_vec, dtype=float)

    # Normalize
    from_vec = from_vec / np.linalg.norm(from_vec)
    to_vec = to_vec / np.linalg.norm(to_vec)

    # Compute rotation axis and angle
    dot = np.dot(from_vec, to_vec)

    # Handle parallel vectors
    if dot > 0.9999:
        return quaternion_identity()

    # Handle opposite vectors
    if dot < -0.9999:
        # Find perpendicular axis
        if abs(from_vec[0]) < 0.9:
            axis = np.cross(from_vec, np.array([1, 0, 0]))
        else:
            axis = np.cross(from_vec, np.array([0, 1, 0]))
        axis = axis / np.linalg.norm(axis)
        return Quaternion.from_axis_angle(axis, 180.0)

    # General case
    axis = np.cross(from_vec, to_vec)
    angle = math.degrees(math.acos(dot))

    return Quaternion.from_axis_angle(axis, angle)
