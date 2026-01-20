"""
Comprehensive tests for quaternion mathematics.

Tests cover:
- Quaternion creation and basic operations
- Euler angle conversions
- Axis-angle conversions
- Quaternion multiplication and composition
- Vector rotation
- SLERP interpolation
- Edge cases and numerical stability
- Gimbal lock scenarios
"""

import pytest
import numpy as np
import math
import sys
import os

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from hybrid.utils.quaternion import (
    Quaternion,
    quaternion_identity,
    quaternion_from_to
)


class TestQuaternionCreation:
    """Test quaternion creation and initialization"""

    def test_default_constructor(self):
        """Test default quaternion is identity"""
        q = Quaternion()
        assert q.w == 1.0
        assert q.x == 0.0
        assert q.y == 0.0
        assert q.z == 0.0
        assert q.is_unit()

    def test_component_constructor(self):
        """Test creating quaternion from components"""
        q = Quaternion(0.5, 0.5, 0.5, 0.5)
        assert q.w == 0.5
        assert q.x == 0.5
        assert q.y == 0.5
        assert q.z == 0.5
        assert q.is_unit()

    def test_identity_function(self):
        """Test identity quaternion helper"""
        q = quaternion_identity()
        assert q.w == 1.0
        assert q.x == 0.0
        assert q.y == 0.0
        assert q.z == 0.0


class TestEulerConversion:
    """Test Euler angle conversions"""

    def test_euler_identity(self):
        """Test zero Euler angles give identity quaternion"""
        q = Quaternion.from_euler(0, 0, 0)
        assert abs(q.w - 1.0) < 1e-10
        assert abs(q.x) < 1e-10
        assert abs(q.y) < 1e-10
        assert abs(q.z) < 1e-10

    def test_euler_pitch_only(self):
        """Test pure pitch rotation"""
        q = Quaternion.from_euler(90, 0, 0)
        pitch, yaw, roll = q.to_euler()
        assert abs(pitch - 90.0) < 1e-6
        assert abs(yaw) < 1e-6
        assert abs(roll) < 1e-6

    def test_euler_yaw_only(self):
        """Test pure yaw rotation"""
        q = Quaternion.from_euler(0, 45, 0)
        pitch, yaw, roll = q.to_euler()
        assert abs(pitch) < 1e-6
        assert abs(yaw - 45.0) < 1e-6
        assert abs(roll) < 1e-6

    def test_euler_roll_only(self):
        """Test pure roll rotation"""
        q = Quaternion.from_euler(0, 0, 30)
        pitch, yaw, roll = q.to_euler()
        assert abs(pitch) < 1e-6
        assert abs(yaw) < 1e-6
        assert abs(roll - 30.0) < 1e-6

    def test_euler_roundtrip(self):
        """Test Euler -> Quaternion -> Euler preserves angles"""
        original_pitch, original_yaw, original_roll = 30.0, 45.0, 15.0
        q = Quaternion.from_euler(original_pitch, original_yaw, original_roll)
        pitch, yaw, roll = q.to_euler()

        assert abs(pitch - original_pitch) < 1e-6
        assert abs(yaw - original_yaw) < 1e-6
        assert abs(roll - original_roll) < 1e-6

    def test_euler_gimbal_lock_90(self):
        """Test gimbal lock at pitch = 90 degrees"""
        q = Quaternion.from_euler(90, 45, 30)
        pitch, yaw, roll = q.to_euler()
        # At gimbal lock, pitch should be 90 but yaw and roll combine
        assert abs(pitch - 90.0) < 1e-6

    def test_euler_gimbal_lock_neg90(self):
        """Test gimbal lock at pitch = -90 degrees"""
        q = Quaternion.from_euler(-90, 45, 30)
        pitch, yaw, roll = q.to_euler()
        # At gimbal lock, pitch should be -90
        assert abs(pitch - (-90.0)) < 1e-6

    def test_euler_large_angles(self):
        """Test with angles > 180 degrees"""
        q = Quaternion.from_euler(270, 0, 0)
        pitch, yaw, roll = q.to_euler()
        # 270 degrees = -90 degrees
        assert abs(pitch - (-90.0)) < 1e-6


class TestAxisAngleConversion:
    """Test axis-angle conversions"""

    def test_axis_angle_identity(self):
        """Test zero angle gives identity"""
        q = Quaternion.from_axis_angle([1, 0, 0], 0)
        assert q.is_unit()
        assert abs(q.w - 1.0) < 1e-10

    def test_axis_angle_x_rotation(self):
        """Test rotation around X axis"""
        q = Quaternion.from_axis_angle([1, 0, 0], 90)
        axis, angle = q.to_axis_angle()
        assert abs(axis[0] - 1.0) < 1e-6
        assert abs(axis[1]) < 1e-6
        assert abs(axis[2]) < 1e-6
        assert abs(angle - 90.0) < 1e-6

    def test_axis_angle_y_rotation(self):
        """Test rotation around Y axis"""
        q = Quaternion.from_axis_angle([0, 1, 0], 45)
        axis, angle = q.to_axis_angle()
        assert abs(axis[0]) < 1e-6
        assert abs(axis[1] - 1.0) < 1e-6
        assert abs(axis[2]) < 1e-6
        assert abs(angle - 45.0) < 1e-6

    def test_axis_angle_arbitrary_axis(self):
        """Test rotation around arbitrary axis"""
        original_axis = np.array([1, 1, 1]) / np.sqrt(3)
        q = Quaternion.from_axis_angle(original_axis, 120)
        axis, angle = q.to_axis_angle()

        # Check axis is preserved
        assert np.linalg.norm(axis - original_axis) < 1e-6
        assert abs(angle - 120.0) < 1e-6

    def test_axis_angle_auto_normalize(self):
        """Test that axis is automatically normalized"""
        q = Quaternion.from_axis_angle([2, 0, 0], 90)  # Unnormalized axis
        assert q.is_unit()


class TestQuaternionOperations:
    """Test quaternion operations"""

    def test_normalize(self):
        """Test quaternion normalization"""
        q = Quaternion(1, 1, 1, 1)  # Not unit quaternion
        assert not q.is_unit()
        q.normalize()
        assert q.is_unit()
        assert abs(q.magnitude() - 1.0) < 1e-10

    def test_normalized_copy(self):
        """Test normalized() returns new quaternion"""
        q = Quaternion(1, 1, 1, 1)
        q_norm = q.normalized()
        assert q_norm.is_unit()
        assert not q.is_unit()  # Original unchanged

    def test_conjugate(self):
        """Test quaternion conjugate"""
        q = Quaternion(0.5, 0.5, 0.5, 0.5)
        q_conj = q.conjugate()
        assert q_conj.w == 0.5
        assert q_conj.x == -0.5
        assert q_conj.y == -0.5
        assert q_conj.z == -0.5

    def test_inverse(self):
        """Test quaternion inverse"""
        q = Quaternion.from_euler(30, 45, 15)
        q_inv = q.inverse()
        # q * q^(-1) should be identity
        identity = q * q_inv
        assert abs(identity.w - 1.0) < 1e-6
        assert abs(identity.x) < 1e-6
        assert abs(identity.y) < 1e-6
        assert abs(identity.z) < 1e-6

    def test_magnitude(self):
        """Test quaternion magnitude calculation"""
        q = Quaternion(2, 0, 0, 0)
        assert abs(q.magnitude() - 2.0) < 1e-10

    def test_dot_product(self):
        """Test quaternion dot product"""
        q1 = Quaternion(1, 0, 0, 0)
        q2 = Quaternion(0, 1, 0, 0)
        assert abs(q1.dot(q2)) < 1e-10  # Orthogonal


class TestQuaternionMultiplication:
    """Test quaternion multiplication and composition"""

    def test_multiply_identity(self):
        """Test multiplication by identity"""
        q = Quaternion.from_euler(30, 45, 15)
        identity = quaternion_identity()
        result = q * identity
        assert result == q

    def test_multiply_inverse(self):
        """Test q * q^(-1) = identity"""
        q = Quaternion.from_euler(30, 45, 15)
        q_inv = q.inverse()
        result = q * q_inv
        assert abs(result.w - 1.0) < 1e-6
        assert abs(result.x) < 1e-6
        assert abs(result.y) < 1e-6
        assert abs(result.z) < 1e-6

    def test_multiply_composition(self):
        """Test rotation composition"""
        # Rotate 90 deg around Z, then 90 deg around X
        q1 = Quaternion.from_euler(0, 90, 0)  # Yaw 90
        q2 = Quaternion.from_euler(90, 0, 0)  # Pitch 90
        q_combined = q2 * q1  # Apply q1 first, then q2

        # Verify by rotating a vector
        v = np.array([1, 0, 0])
        v1 = q1.rotate_vector(v)
        v2 = q2.rotate_vector(v1)
        v_combined = q_combined.rotate_vector(v)

        assert np.linalg.norm(v2 - v_combined) < 1e-6

    def test_multiply_preserves_unit(self):
        """Test that multiplying unit quaternions gives unit quaternion"""
        q1 = Quaternion.from_euler(30, 0, 0)
        q2 = Quaternion.from_euler(0, 45, 0)
        result = q1 * q2
        assert result.is_unit()


class TestVectorRotation:
    """Test vector rotation by quaternions"""

    def test_rotate_identity(self):
        """Test identity quaternion doesn't change vector"""
        q = quaternion_identity()
        v = np.array([1, 2, 3])
        v_rotated = q.rotate_vector(v)
        assert np.linalg.norm(v_rotated - v) < 1e-10

    def test_rotate_90_around_z(self):
        """Test 90 degree rotation around Z axis"""
        q = Quaternion.from_axis_angle([0, 0, 1], 90)
        v = np.array([1, 0, 0])
        v_rotated = q.rotate_vector(v)
        expected = np.array([0, 1, 0])
        assert np.linalg.norm(v_rotated - expected) < 1e-6

    def test_rotate_180_around_x(self):
        """Test 180 degree rotation around X axis"""
        q = Quaternion.from_axis_angle([1, 0, 0], 180)
        v = np.array([0, 1, 0])
        v_rotated = q.rotate_vector(v)
        expected = np.array([0, -1, 0])
        assert np.linalg.norm(v_rotated - expected) < 1e-6

    def test_rotate_preserves_magnitude(self):
        """Test rotation preserves vector magnitude"""
        q = Quaternion.from_euler(30, 45, 60)
        v = np.array([3, 4, 5])
        v_rotated = q.rotate_vector(v)
        assert abs(np.linalg.norm(v_rotated) - np.linalg.norm(v)) < 1e-6


class TestSLERP:
    """Test spherical linear interpolation"""

    def test_slerp_endpoints(self):
        """Test SLERP at t=0 and t=1"""
        q1 = Quaternion.from_euler(0, 0, 0)
        q2 = Quaternion.from_euler(90, 0, 0)

        result_0 = Quaternion.slerp(q1, q2, 0.0)
        result_1 = Quaternion.slerp(q1, q2, 1.0)

        # At t=0, should be q1
        assert abs(result_0.w - q1.w) < 1e-6
        assert abs(result_0.x - q1.x) < 1e-6

        # At t=1, should be q2 (or -q2, which is same rotation)
        assert abs(abs(result_1.w) - abs(q2.w)) < 1e-6

    def test_slerp_midpoint(self):
        """Test SLERP at t=0.5"""
        q1 = Quaternion.from_euler(0, 0, 0)
        q2 = Quaternion.from_euler(90, 0, 0)
        result = Quaternion.slerp(q1, q2, 0.5)

        # Should be approximately 45 degrees
        pitch, yaw, roll = result.to_euler()
        assert abs(pitch - 45.0) < 1.0  # Allow some tolerance

    def test_slerp_unit_result(self):
        """Test SLERP always produces unit quaternions"""
        q1 = Quaternion.from_euler(30, 45, 15)
        q2 = Quaternion.from_euler(60, 90, 30)

        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            result = Quaternion.slerp(q1, q2, t)
            assert result.is_unit()

    def test_slerp_clamps_t(self):
        """Test SLERP clamps t to [0, 1]"""
        q1 = Quaternion.from_euler(0, 0, 0)
        q2 = Quaternion.from_euler(90, 0, 0)

        result_neg = Quaternion.slerp(q1, q2, -0.5)
        result_pos = Quaternion.slerp(q1, q2, 1.5)

        # Should clamp to endpoints
        assert abs(result_neg.w - q1.w) < 1e-6
        assert abs(abs(result_pos.w) - abs(q2.w)) < 1e-6


class TestRotationMatrix:
    """Test rotation matrix conversion"""

    def test_rotation_matrix_identity(self):
        """Test identity quaternion gives identity matrix"""
        q = quaternion_identity()
        matrix = q.to_rotation_matrix()
        expected = np.eye(3)
        assert np.linalg.norm(matrix - expected) < 1e-10

    def test_rotation_matrix_orthogonal(self):
        """Test rotation matrix is orthogonal"""
        q = Quaternion.from_euler(30, 45, 60)
        matrix = q.to_rotation_matrix()

        # R * R^T should be identity
        identity = matrix @ matrix.T
        expected = np.eye(3)
        assert np.linalg.norm(identity - expected) < 1e-6

    def test_rotation_matrix_determinant(self):
        """Test rotation matrix has determinant = 1"""
        q = Quaternion.from_euler(30, 45, 60)
        matrix = q.to_rotation_matrix()
        det = np.linalg.det(matrix)
        assert abs(det - 1.0) < 1e-6

    def test_rotation_matrix_rotates_vector(self):
        """Test rotation matrix gives same result as rotate_vector"""
        q = Quaternion.from_euler(30, 45, 60)
        v = np.array([1, 2, 3])

        v_quat = q.rotate_vector(v)
        matrix = q.to_rotation_matrix()
        v_matrix = matrix @ v

        assert np.linalg.norm(v_quat - v_matrix) < 1e-6


class TestQuaternionFromTo:
    """Test quaternion_from_to helper function"""

    def test_from_to_identity(self):
        """Test rotating vector to itself"""
        v = np.array([1, 0, 0])
        q = quaternion_from_to(v, v)
        # Should be close to identity
        assert abs(q.w - 1.0) < 1e-6

    def test_from_to_90_degrees(self):
        """Test 90 degree rotation"""
        v1 = np.array([1, 0, 0])
        v2 = np.array([0, 1, 0])
        q = quaternion_from_to(v1, v2)

        # Verify rotation works
        v1_rotated = q.rotate_vector(v1)
        assert np.linalg.norm(v1_rotated - v2) < 1e-6

    def test_from_to_opposite_vectors(self):
        """Test 180 degree rotation (opposite vectors)"""
        v1 = np.array([1, 0, 0])
        v2 = np.array([-1, 0, 0])
        q = quaternion_from_to(v1, v2)

        v1_rotated = q.rotate_vector(v1)
        assert np.linalg.norm(v1_rotated - v2) < 1e-6


class TestEdgeCases:
    """Test edge cases and numerical stability"""

    def test_zero_quaternion_normalize(self):
        """Test normalizing zero quaternion"""
        q = Quaternion(0, 0, 0, 0)
        q.normalize()
        # Should reset to identity
        assert q.w == 1.0
        assert q.x == 0.0
        assert q.y == 0.0
        assert q.z == 0.0

    def test_very_small_angles(self):
        """Test quaternions with very small angles"""
        q = Quaternion.from_euler(0.001, 0.0, 0.0)
        assert q.is_unit()
        pitch, yaw, roll = q.to_euler()
        assert abs(pitch - 0.001) < 1e-6

    def test_large_angles(self):
        """Test quaternions with angles > 360 degrees"""
        q1 = Quaternion.from_euler(0, 360, 0)
        q2 = Quaternion.from_euler(0, 0, 0)
        # 360 degrees = 0 degrees
        # Note: quaternions may differ but represent same rotation
        assert q1.is_unit()

    def test_equality_operator(self):
        """Test quaternion equality"""
        q1 = Quaternion(1, 0, 0, 0)
        q2 = Quaternion(1, 0, 0, 0)
        q3 = Quaternion(0, 1, 0, 0)

        assert q1 == q2
        assert not (q1 == q3)

    def test_string_representation(self):
        """Test string methods"""
        q = Quaternion(1, 0, 0, 0)
        str_repr = str(q)
        repr_str = repr(q)

        assert "Quat" in str_repr or "Quaternion" in str_repr
        assert "1.0" in str_repr or "1.00" in str_repr


class TestScalarOperations:
    """Test scalar arithmetic operations"""

    def test_scalar_multiplication_left(self):
        """Test scalar * quaternion"""
        q = Quaternion(1, 0, 0, 0)
        result = 2.0 * q
        assert result.w == 2.0
        assert result.x == 0.0

    def test_scalar_multiplication_right(self):
        """Test quaternion * scalar"""
        q = Quaternion(1, 0, 0, 0)
        result = q.scale(2.0)
        assert result.w == 2.0
        assert result.x == 0.0

    def test_quaternion_addition(self):
        """Test quaternion + quaternion"""
        q1 = Quaternion(1, 0, 0, 0)
        q2 = Quaternion(0, 1, 0, 0)
        result = q1 + q2
        assert result.w == 1.0
        assert result.x == 1.0
        assert result.y == 0.0
        assert result.z == 0.0

    def test_quaternion_subtraction(self):
        """Test quaternion - quaternion"""
        q1 = Quaternion(2, 1, 0, 0)
        q2 = Quaternion(1, 0.5, 0, 0)
        result = q1 - q2
        assert result.w == 1.0
        assert result.x == 0.5
        assert result.y == 0.0
        assert result.z == 0.0
