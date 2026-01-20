"""
Comprehensive test suite for Quaternion class.

Tests all quaternion operations, edge cases, and numerical stability.
"""

import pytest
import math
import sys
import os

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from hybrid.utils.quaternion import (
    Quaternion,
    integrate_angular_velocity,
    quaternion_between_vectors
)


# Tolerance for floating point comparisons
TOLERANCE = 1e-6


def approx_equal(a: float, b: float, tol: float = TOLERANCE) -> bool:
    """Check if two values are approximately equal."""
    return abs(a - b) < tol


def approx_equal_vector(v1: tuple, v2: tuple, tol: float = TOLERANCE) -> bool:
    """Check if two 3D vectors are approximately equal."""
    return all(approx_equal(a, b, tol) for a, b in zip(v1, v2))


class TestQuaternionBasics:
    """Test basic quaternion creation and properties."""

    def test_identity_creation(self):
        """Test identity quaternion creation."""
        q = Quaternion()
        assert q.w == 1.0
        assert q.x == 0.0
        assert q.y == 0.0
        assert q.z == 0.0

    def test_identity_factory(self):
        """Test identity factory method."""
        q = Quaternion.identity()
        assert q.w == 1.0
        assert q.x == 0.0
        assert q.y == 0.0
        assert q.z == 0.0

    def test_custom_creation(self):
        """Test creating quaternion with specific values."""
        q = Quaternion(0.707, 0.707, 0.0, 0.0)
        assert approx_equal(q.w, 0.707)
        assert approx_equal(q.x, 0.707)
        assert q.y == 0.0
        assert q.z == 0.0

    def test_magnitude_identity(self):
        """Test magnitude of identity quaternion."""
        q = Quaternion.identity()
        assert approx_equal(q.magnitude(), 1.0)

    def test_magnitude_custom(self):
        """Test magnitude calculation."""
        q = Quaternion(1.0, 2.0, 3.0, 4.0)
        expected = math.sqrt(1 + 4 + 9 + 16)  # sqrt(30)
        assert approx_equal(q.magnitude(), expected)

    def test_normalization(self):
        """Test quaternion normalization."""
        q = Quaternion(1.0, 2.0, 3.0, 4.0)
        q_norm = q.normalize()
        assert approx_equal(q_norm.magnitude(), 1.0)

    def test_copy(self):
        """Test quaternion copying."""
        q1 = Quaternion(1.0, 2.0, 3.0, 4.0)
        q2 = q1.copy()
        assert q1 == q2
        assert q1 is not q2  # Different objects

    def test_equality(self):
        """Test quaternion equality comparison."""
        q1 = Quaternion(1.0, 0.0, 0.0, 0.0)
        q2 = Quaternion(1.0, 0.0, 0.0, 0.0)
        q3 = Quaternion(0.5, 0.5, 0.5, 0.5)
        assert q1 == q2
        assert q1 != q3


class TestEulerConversion:
    """Test conversion between Euler angles and quaternions."""

    def test_identity_from_euler(self):
        """Test identity quaternion from zero Euler angles."""
        q = Quaternion.from_euler(0.0, 0.0, 0.0)
        assert approx_equal(q.w, 1.0)
        assert approx_equal(q.x, 0.0)
        assert approx_equal(q.y, 0.0)
        assert approx_equal(q.z, 0.0)

    def test_euler_round_trip(self):
        """Test Euler -> Quaternion -> Euler conversion."""
        pitch, yaw, roll = 15.0, 45.0, 30.0
        q = Quaternion.from_euler(pitch, yaw, roll)
        p2, y2, r2 = q.to_euler()

        assert approx_equal(pitch, p2, 1e-4)
        assert approx_equal(yaw, y2, 1e-4)
        assert approx_equal(roll, r2, 1e-4)

    def test_90_degree_pitch(self):
        """Test 90 degree pitch rotation."""
        q = Quaternion.from_euler(90.0, 0.0, 0.0)
        pitch, yaw, roll = q.to_euler()
        assert approx_equal(pitch, 90.0, 1e-3)
        assert approx_equal(yaw, 0.0, 1e-3)
        assert approx_equal(roll, 0.0, 1e-3)

    def test_90_degree_yaw(self):
        """Test 90 degree yaw rotation."""
        q = Quaternion.from_euler(0.0, 90.0, 0.0)
        pitch, yaw, roll = q.to_euler()
        assert approx_equal(pitch, 0.0, 1e-3)
        assert approx_equal(yaw, 90.0, 1e-3)
        assert approx_equal(roll, 0.0, 1e-3)

    def test_90_degree_roll(self):
        """Test 90 degree roll rotation."""
        q = Quaternion.from_euler(0.0, 0.0, 90.0)
        pitch, yaw, roll = q.to_euler()
        assert approx_equal(pitch, 0.0, 1e-3)
        assert approx_equal(yaw, 0.0, 1e-3)
        assert approx_equal(roll, 90.0, 1e-3)

    def test_gimbal_lock_positive(self):
        """Test gimbal lock case at +90° pitch."""
        q = Quaternion.from_euler(90.0, 45.0, 30.0)
        pitch, yaw, roll = q.to_euler()

        # Pitch should be 90 degrees
        assert approx_equal(pitch, 90.0, 1e-3)

        # At gimbal lock, yaw and roll combine - exact values may differ
        # but the rotation should be equivalent

    def test_gimbal_lock_negative(self):
        """Test gimbal lock case at -90° pitch."""
        q = Quaternion.from_euler(-90.0, 45.0, 30.0)
        pitch, yaw, roll = q.to_euler()

        # Pitch should be -90 degrees
        assert approx_equal(pitch, -90.0, 1e-3)

    def test_radians_mode(self):
        """Test Euler conversion with radians."""
        pitch_rad = math.radians(30.0)
        yaw_rad = math.radians(45.0)
        roll_rad = math.radians(60.0)

        q = Quaternion.from_euler(pitch_rad, yaw_rad, roll_rad, degrees=False)
        p2, y2, r2 = q.to_euler(degrees=False)

        assert approx_equal(pitch_rad, p2, 1e-4)
        assert approx_equal(yaw_rad, y2, 1e-4)
        assert approx_equal(roll_rad, r2, 1e-4)


class TestQuaternionOperations:
    """Test quaternion arithmetic operations."""

    def test_conjugate(self):
        """Test quaternion conjugate."""
        q = Quaternion(1.0, 2.0, 3.0, 4.0)
        q_conj = q.conjugate()
        assert q_conj.w == 1.0
        assert q_conj.x == -2.0
        assert q_conj.y == -3.0
        assert q_conj.z == -4.0

    def test_inverse_identity(self):
        """Test inverse of identity is identity."""
        q = Quaternion.identity()
        q_inv = q.inverse()
        assert q == q_inv

    def test_inverse_unit_quaternion(self):
        """Test inverse of unit quaternion equals conjugate."""
        q = Quaternion.from_euler(30.0, 45.0, 60.0)
        q_inv = q.inverse()
        q_conj = q.conjugate()

        # For unit quaternion, inverse should equal conjugate
        assert approx_equal(q_inv.w, q_conj.w)
        assert approx_equal(q_inv.x, q_conj.x)
        assert approx_equal(q_inv.y, q_conj.y)
        assert approx_equal(q_inv.z, q_conj.z)

    def test_multiplication_identity(self):
        """Test multiplication with identity."""
        q = Quaternion.from_euler(30.0, 45.0, 60.0)
        identity = Quaternion.identity()

        result1 = q * identity
        result2 = identity * q

        assert approx_equal(result1.w, q.w)
        assert approx_equal(result1.x, q.x)
        assert approx_equal(result1.y, q.y)
        assert approx_equal(result1.z, q.z)

        assert approx_equal(result2.w, q.w)
        assert approx_equal(result2.x, q.x)
        assert approx_equal(result2.y, q.y)
        assert approx_equal(result2.z, q.z)

    def test_multiplication_composition(self):
        """Test quaternion multiplication composes rotations."""
        # 90° pitch then 90° yaw
        q_pitch = Quaternion.from_euler(90.0, 0.0, 0.0)
        q_yaw = Quaternion.from_euler(0.0, 90.0, 0.0)

        # Compose rotations
        q_combined = q_pitch * q_yaw

        # Verify the combined rotation is correct
        # by rotating a test vector
        v_test = (1.0, 0.0, 0.0)  # X-axis vector

        # Apply yaw first (rotate around Z)
        v_after_yaw = q_yaw.rotate_vector(v_test)

        # Then pitch (rotate around Y)
        v_final = q_pitch.rotate_vector(v_after_yaw)

        # Should equal direct combined rotation
        v_combined = q_combined.rotate_vector(v_test)

        assert approx_equal_vector(v_final, v_combined, 1e-4)

    def test_dot_product_identity(self):
        """Test dot product with identity."""
        q = Quaternion.from_euler(30.0, 45.0, 60.0).normalize()
        identity = Quaternion.identity()

        dot = q.dot(identity)
        # Dot product should be close to w component for unit quaternions
        assert approx_equal(dot, q.w, 1e-4)

    def test_dot_product_same(self):
        """Test dot product of quaternion with itself."""
        q = Quaternion.from_euler(30.0, 45.0, 60.0).normalize()
        dot = q.dot(q)
        # For unit quaternion, dot with itself should be 1
        assert approx_equal(dot, 1.0, 1e-4)


class TestVectorRotation:
    """Test rotating vectors with quaternions."""

    def test_rotate_identity(self):
        """Test rotating vector with identity quaternion."""
        q = Quaternion.identity()
        v = (1.0, 2.0, 3.0)
        v_rotated = q.rotate_vector(v)
        assert approx_equal_vector(v, v_rotated)

    def test_rotate_90_yaw(self):
        """Test 90° yaw rotates X-axis to Y-axis."""
        q = Quaternion.from_euler(0.0, 90.0, 0.0)
        v = (1.0, 0.0, 0.0)  # X-axis
        v_rotated = q.rotate_vector(v)

        # Should point along Y-axis (approximately)
        assert approx_equal(v_rotated[0], 0.0, 1e-4)
        assert approx_equal(v_rotated[1], 1.0, 1e-4)
        assert approx_equal(v_rotated[2], 0.0, 1e-4)

    def test_rotate_90_pitch(self):
        """Test 90° pitch rotates X-axis to Z-axis."""
        q = Quaternion.from_euler(90.0, 0.0, 0.0)
        v = (1.0, 0.0, 0.0)  # X-axis
        v_rotated = q.rotate_vector(v)

        # Should point along Z-axis (approximately)
        assert approx_equal(v_rotated[0], 0.0, 1e-4)
        assert approx_equal(v_rotated[1], 0.0, 1e-4)
        assert approx_equal(abs(v_rotated[2]), 1.0, 1e-4)

    def test_rotate_180(self):
        """Test 180° rotation reverses vector."""
        q = Quaternion.from_euler(0.0, 180.0, 0.0)
        v = (1.0, 0.0, 0.0)
        v_rotated = q.rotate_vector(v)

        # Should be reversed
        assert approx_equal(v_rotated[0], -1.0, 1e-4)
        assert approx_equal(v_rotated[1], 0.0, 1e-4)
        assert approx_equal(v_rotated[2], 0.0, 1e-4)

    def test_rotate_preserves_magnitude(self):
        """Test rotation preserves vector magnitude."""
        q = Quaternion.from_euler(30.0, 45.0, 60.0)
        v = (3.0, 4.0, 5.0)
        v_rotated = q.rotate_vector(v)

        mag_original = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        mag_rotated = math.sqrt(v_rotated[0]**2 + v_rotated[1]**2 + v_rotated[2]**2)

        assert approx_equal(mag_original, mag_rotated, 1e-4)


class TestSLERP:
    """Test spherical linear interpolation."""

    def test_slerp_endpoints(self):
        """Test SLERP at endpoints returns input quaternions."""
        q1 = Quaternion.from_euler(0.0, 0.0, 0.0)
        q2 = Quaternion.from_euler(90.0, 0.0, 0.0)

        result_start = Quaternion.slerp(q1, q2, 0.0)
        result_end = Quaternion.slerp(q1, q2, 1.0)

        # At t=0, should match q1
        p1, y1, r1 = result_start.to_euler()
        assert approx_equal(p1, 0.0, 1e-3)

        # At t=1, should match q2
        p2, y2, r2 = result_end.to_euler()
        assert approx_equal(p2, 90.0, 1e-3)

    def test_slerp_midpoint(self):
        """Test SLERP at midpoint."""
        q1 = Quaternion.from_euler(0.0, 0.0, 0.0)
        q2 = Quaternion.from_euler(90.0, 0.0, 0.0)

        result_mid = Quaternion.slerp(q1, q2, 0.5)
        pitch, yaw, roll = result_mid.to_euler()

        # At t=0.5, should be approximately 45°
        assert approx_equal(pitch, 45.0, 1.0)  # Looser tolerance for interpolation

    def test_slerp_smooth(self):
        """Test SLERP produces smooth interpolation."""
        q1 = Quaternion.from_euler(0.0, 0.0, 0.0)
        q2 = Quaternion.from_euler(90.0, 0.0, 0.0)

        # Sample at multiple points
        angles = []
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            q_interp = Quaternion.slerp(q1, q2, t)
            pitch, _, _ = q_interp.to_euler()
            angles.append(pitch)

        # Check monotonic increase
        for i in range(len(angles) - 1):
            assert angles[i] <= angles[i + 1] + 1.0  # Allow small numerical errors

    def test_slerp_clamps_t(self):
        """Test SLERP clamps t parameter to [0,1]."""
        q1 = Quaternion.from_euler(0.0, 0.0, 0.0)
        q2 = Quaternion.from_euler(90.0, 0.0, 0.0)

        # t < 0 should give q1
        result = Quaternion.slerp(q1, q2, -0.5)
        pitch, _, _ = result.to_euler()
        assert approx_equal(pitch, 0.0, 1e-3)

        # t > 1 should give q2
        result = Quaternion.slerp(q1, q2, 1.5)
        pitch, _, _ = result.to_euler()
        assert approx_equal(pitch, 90.0, 1e-3)


class TestAxisAngle:
    """Test axis-angle representation."""

    def test_from_axis_angle_x(self):
        """Test creating quaternion from X-axis rotation."""
        q = Quaternion.from_axis_angle((1, 0, 0), 90.0)
        pitch, yaw, roll = q.to_euler()
        # 90° around X is 90° roll
        assert approx_equal(roll, 90.0, 1e-3)

    def test_from_axis_angle_y(self):
        """Test creating quaternion from Y-axis rotation."""
        q = Quaternion.from_axis_angle((0, 1, 0), 90.0)
        pitch, yaw, roll = q.to_euler()
        # 90° around Y is 90° pitch
        assert approx_equal(pitch, 90.0, 1e-3)

    def test_from_axis_angle_z(self):
        """Test creating quaternion from Z-axis rotation."""
        q = Quaternion.from_axis_angle((0, 0, 1), 90.0)
        pitch, yaw, roll = q.to_euler()
        # 90° around Z is 90° yaw
        assert approx_equal(yaw, 90.0, 1e-3)

    def test_axis_angle_round_trip(self):
        """Test axis-angle round trip conversion."""
        axis_in = (0.577, 0.577, 0.577)  # Normalized (1,1,1)
        angle_in = 60.0

        q = Quaternion.from_axis_angle(axis_in, angle_in)
        axis_out, angle_out = q.to_axis_angle()

        # Angle should match
        assert approx_equal(angle_in, angle_out, 1e-3)

        # Axis should match (or be negated with angle adjusted)
        assert approx_equal_vector(axis_in, axis_out, 1e-3) or \
               approx_equal_vector((-axis_in[0], -axis_in[1], -axis_in[2]),
                                 axis_out, 1e-3)


class TestAngularVelocityIntegration:
    """Test integrating angular velocity."""

    def test_integration_zero_velocity(self):
        """Test integration with zero angular velocity."""
        q = Quaternion.from_euler(30.0, 45.0, 60.0)
        angular_velocity = (0.0, 0.0, 0.0)

        q_new = integrate_angular_velocity(q, angular_velocity, 0.1)

        # Should remain unchanged
        p1, y1, r1 = q.to_euler()
        p2, y2, r2 = q_new.to_euler()

        assert approx_equal(p1, p2, 1e-3)
        assert approx_equal(y1, y2, 1e-3)
        assert approx_equal(r1, r2, 1e-3)

    def test_integration_pitch_rate(self):
        """Test integration with pitch rate."""
        q = Quaternion.identity()
        # 10 degrees/second pitch rate
        pitch_rate_rad = math.radians(10.0)
        angular_velocity = (0.0, pitch_rate_rad, 0.0)

        # Integrate for 1 second
        q_new = q
        for _ in range(10):
            q_new = integrate_angular_velocity(q_new, angular_velocity, 0.1)

        pitch, _, _ = q_new.to_euler()

        # Should be approximately 10 degrees
        assert approx_equal(pitch, 10.0, 0.5)  # Tolerance for numerical integration

    def test_integration_maintains_normalization(self):
        """Test integration maintains unit quaternion."""
        q = Quaternion.identity()
        angular_velocity = (math.radians(5), math.radians(10), math.radians(15))

        # Integrate for many steps
        q_new = q
        for _ in range(100):
            q_new = integrate_angular_velocity(q_new, angular_velocity, 0.01)

        # Should still be unit quaternion
        assert approx_equal(q_new.magnitude(), 1.0, 1e-4)


class TestQuaternionBetweenVectors:
    """Test quaternion calculation between vectors."""

    def test_between_same_vectors(self):
        """Test quaternion between identical vectors."""
        v = (1.0, 0.0, 0.0)
        q = quaternion_between_vectors(v, v)

        # Should be identity (no rotation needed)
        assert approx_equal(q.w, 1.0, 1e-6)

    def test_between_opposite_vectors(self):
        """Test quaternion between opposite vectors."""
        v1 = (1.0, 0.0, 0.0)
        v2 = (-1.0, 0.0, 0.0)

        q = quaternion_between_vectors(v1, v2)

        # Should rotate 180 degrees
        v_rotated = q.rotate_vector(v1)
        assert approx_equal_vector(v_rotated, v2, 1e-4)

    def test_between_perpendicular_vectors(self):
        """Test quaternion between perpendicular vectors."""
        v1 = (1.0, 0.0, 0.0)
        v2 = (0.0, 1.0, 0.0)

        q = quaternion_between_vectors(v1, v2)

        # Should rotate v1 to v2
        v_rotated = q.rotate_vector(v1)
        assert approx_equal_vector(v_rotated, v2, 1e-4)

    def test_between_arbitrary_vectors(self):
        """Test quaternion between arbitrary vectors."""
        v1 = (1.0, 0.0, 0.0)
        v2 = (0.577, 0.577, 0.577)  # Normalized (1, 1, 1)

        q = quaternion_between_vectors(v1, v2)

        # Should rotate v1 to align with v2
        v_rotated = q.rotate_vector(v1)

        # Normalize both for comparison
        v2_len = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
        v2_norm = (v2[0]/v2_len, v2[1]/v2_len, v2[2]/v2_len)

        v_rot_len = math.sqrt(v_rotated[0]**2 + v_rotated[1]**2 + v_rotated[2]**2)
        v_rot_norm = (v_rotated[0]/v_rot_len, v_rotated[1]/v_rot_len, v_rotated[2]/v_rot_len)

        assert approx_equal_vector(v_rot_norm, v2_norm, 1e-3)


class TestEdgeCases:
    """Test edge cases and numerical stability."""

    def test_360_degree_wrap(self):
        """Test 360° angle wrapping."""
        q1 = Quaternion.from_euler(0.0, 0.0, 0.0)
        q2 = Quaternion.from_euler(360.0, 0.0, 0.0)

        # Should represent same rotation
        pitch1, yaw1, roll1 = q1.to_euler()
        pitch2, yaw2, roll2 = q2.to_euler()

        # Angles should be equivalent (modulo 360)
        assert approx_equal(abs(pitch1 - pitch2) % 360, 0.0, 1e-3)

    def test_very_small_angles(self):
        """Test very small angle rotations."""
        q = Quaternion.from_euler(0.001, 0.001, 0.001)
        pitch, yaw, roll = q.to_euler()

        assert approx_equal(pitch, 0.001, 1e-6)
        assert approx_equal(yaw, 0.001, 1e-6)
        assert approx_equal(roll, 0.001, 1e-6)

    def test_normalize_degenerate(self):
        """Test normalizing degenerate (zero) quaternion."""
        q = Quaternion(0.0, 0.0, 0.0, 0.0)
        q_norm = q.normalize()

        # Should return identity
        assert approx_equal(q_norm.w, 1.0)
        assert approx_equal(q_norm.x, 0.0)
        assert approx_equal(q_norm.y, 0.0)
        assert approx_equal(q_norm.z, 0.0)

    def test_inverse_degenerate(self):
        """Test inverse of degenerate quaternion."""
        q = Quaternion(0.0, 0.0, 0.0, 0.0)
        q_inv = q.inverse()

        # Should return identity
        assert approx_equal(q_inv.w, 1.0)

    def test_multiple_rotations_stability(self):
        """Test numerical stability over many rotations."""
        q = Quaternion.identity()
        angular_velocity = (math.radians(1), math.radians(1), math.radians(1))

        # Apply many small rotations
        for _ in range(1000):
            q = integrate_angular_velocity(q, angular_velocity, 0.01)

        # Should still be unit quaternion
        assert approx_equal(q.magnitude(), 1.0, 1e-4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
