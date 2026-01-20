"""
Test demonstrating that quaternions eliminate gimbal lock.

Gimbal lock occurs with Euler angles when pitch approaches ±90°.
Quaternions handle all orientations smoothly without this limitation.
"""

import pytest
import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT_DIR)

from hybrid.ship import Ship


class TestGimbalLockElimination:
    """Demonstrate quaternion-based attitude eliminates gimbal lock."""

    def test_no_gimbal_lock_at_90_degrees(self):
        """Test ship can operate normally at pitch=90° (old gimbal lock condition)"""
        ship = Ship("test_ship", {"orientation": {"pitch": 89.5, "yaw": 0, "roll": 0}})

        # Set angular velocities in all axes
        ship.angular_velocity["pitch"] = 1.0
        ship.angular_velocity["yaw"] = 5.0   # This would be problematic with Euler at pitch=90°
        ship.angular_velocity["roll"] = 3.0

        # Update for several ticks
        for _ in range(10):
            ship.tick(0.1)

        # Ship should update normally without NaN or crashes
        # S3: With quaternions, no gimbal lock warnings are generated
        assert ship.quaternion.is_unit()  # Quaternion remains normalized
        assert abs(ship.orientation["pitch"]) < 100  # Pitch changed but stayed reasonable

    def test_smooth_rotation_through_gimbal_lock_zone(self):
        """Test smooth rotation through pitch=90° (former gimbal lock)"""
        ship = Ship("test_ship", {"orientation": {"pitch": 80, "yaw": 0, "roll": 0}})

        # Rotate through the old gimbal lock zone
        ship.angular_velocity["pitch"] = 10.0  # Will pass through 90 degrees

        positions = []
        for _ in range(20):
            ship.tick(0.1)
            positions.append(ship.orientation["pitch"])

        # Should smoothly transition through 90 degrees
        # No sudden jumps or NaN values
        for i in range(1, len(positions)):
            delta = abs(positions[i] - positions[i-1])
            assert delta < 2.0  # Smooth change, no sudden jumps
            assert -180 <= positions[i] <= 180  # Always normalized

    def test_quaternion_always_unit_length(self):
        """Test quaternion maintains unit length through all rotations"""
        ship = Ship("test_ship", {})

        # Set aggressive angular velocities
        ship.angular_velocity["pitch"] = 45.0
        ship.angular_velocity["yaw"] = 30.0
        ship.angular_velocity["roll"] = 60.0

        # Run for extended period
        for _ in range(100):
            ship.tick(0.1)
            assert ship.quaternion.is_unit(epsilon=1e-4)  # Should stay normalized

    def test_combined_rotations_stable(self):
        """Test combined rotations remain stable (no gimbal lock)"""
        ship = Ship("test_ship", {"orientation": {"pitch": 85, "yaw": 45, "roll": 30}})

        # Start near gimbal lock with combined rotations
        ship.angular_velocity["pitch"] = 2.0
        ship.angular_velocity["yaw"] = 10.0
        ship.angular_velocity["roll"] = -5.0

        # Should handle this gracefully
        for _ in range(50):
            ship.tick(0.1)

        # Verify stability
        assert ship.quaternion.is_unit()
        assert all(abs(ship.orientation[k]) <= 180 for k in ["pitch", "yaw", "roll"])

    def test_no_gimbal_lock_warnings(self):
        """Verify quaternion system handles extreme angles without issues"""
        ship = Ship("test_ship", {})

        # Deliberately go to old gimbal lock angle
        ship.angular_velocity["pitch"] = 100.0  # Will exceed 90 degrees

        # Run simulation
        for _ in range(15):
            ship.tick(0.1)

        # S3: Quaternion system should handle this gracefully
        # No crashes, NaN values, or instability
        assert ship.quaternion.is_unit()
        assert all(abs(ship.orientation[k]) <= 180 for k in ["pitch", "yaw", "roll"])
