# tests/systems/test_rcs_system.py
"""Tests for RCS (Reaction Control System) torque-based attitude control."""

import pytest
import math
import numpy as np
from hybrid.systems.rcs_system import RCSSystem, RCSThruster
from hybrid.utils.quaternion import Quaternion


class MockShip:
    """Mock ship for testing RCS system."""
    
    def __init__(self):
        self.id = "test_ship"
        self.mass = 10000.0  # 10 tons
        self.moment_of_inertia = 50000.0  # kg·m²
        self.orientation = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.angular_velocity = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.quaternion = Quaternion.from_euler(0, 0, 0)
        self.systems = {}


class MockEventBus:
    """Mock event bus for testing."""
    
    def __init__(self):
        self.events = []
    
    def publish(self, event_type, data):
        self.events.append((event_type, data))


class TestRCSThruster:
    """Tests for individual RCS thruster."""
    
    def test_thruster_creation(self):
        """Test thruster initialization from config."""
        config = {
            "id": "bow_port",
            "position": [10.0, -5.0, 0.0],
            "direction": [0.0, 1.0, 0.0],
            "max_thrust": 1000.0,
            "fuel_consumption": 0.1
        }
        thruster = RCSThruster(config)
        
        assert thruster.id == "bow_port"
        assert thruster.max_thrust == 1000.0
        assert thruster.fuel_consumption == 0.1
        assert np.allclose(thruster.position, [10.0, -5.0, 0.0])
        assert np.allclose(thruster.direction, [0.0, 1.0, 0.0])
    
    def test_thruster_force(self):
        """Test thruster force calculation."""
        config = {
            "id": "test",
            "position": [0, 0, 0],
            "direction": [1, 0, 0],
            "max_thrust": 1000.0
        }
        thruster = RCSThruster(config)
        
        # Zero throttle = zero force
        assert np.allclose(thruster.get_force(), [0, 0, 0])
        
        # Full throttle
        thruster.throttle = 1.0
        force = thruster.get_force()
        assert np.allclose(force, [1000.0, 0, 0])
        
        # Half throttle
        thruster.throttle = 0.5
        force = thruster.get_force()
        assert np.allclose(force, [500.0, 0, 0])
    
    def test_thruster_torque(self):
        """Test thruster torque calculation (τ = r × F)."""
        # Thruster at position [10, 0, 0] pushing in Y direction
        # Should produce torque in Z (yaw)
        config = {
            "id": "yaw_test",
            "position": [10.0, 0.0, 0.0],
            "direction": [0, 1, 0],
            "max_thrust": 100.0
        }
        thruster = RCSThruster(config)
        thruster.throttle = 1.0
        
        torque = thruster.get_torque()
        # r × F = [10,0,0] × [0,100,0] = [0,0,1000]
        assert np.allclose(torque, [0, 0, 1000], atol=0.1)


class TestRCSSystem:
    """Tests for RCS system."""
    
    def test_rcs_initialization(self):
        """Test RCS system initialization with default thrusters."""
        rcs = RCSSystem({})
        
        assert rcs.enabled
        assert len(rcs.thrusters) > 0  # Default thrusters created
        assert rcs.control_mode == "rate"
        assert rcs.attitude_target is None
    
    def test_rcs_custom_thrusters(self):
        """Test RCS with custom thruster config."""
        config = {
            "thrusters": [
                {"id": "t1", "position": [1, 0, 0], "direction": [0, 1, 0], "max_thrust": 500},
                {"id": "t2", "position": [-1, 0, 0], "direction": [0, -1, 0], "max_thrust": 500},
            ]
        }
        rcs = RCSSystem(config)
        
        assert len(rcs.thrusters) == 2
        assert rcs.thrusters[0].id == "t1"
        assert rcs.thrusters[1].id == "t2"
    
    def test_set_attitude_target(self):
        """Test setting attitude target."""
        rcs = RCSSystem({})
        
        result = rcs.set_attitude_target({"pitch": 30.0, "yaw": 45.0, "roll": 0.0})
        
        assert "status" in result
        assert rcs.control_mode == "attitude"
        assert rcs.attitude_target["pitch"] == 30.0
        assert rcs.attitude_target["yaw"] == 45.0
    
    def test_set_angular_velocity_target(self):
        """Test setting angular velocity target."""
        rcs = RCSSystem({})
        
        result = rcs.set_angular_velocity_target({"pitch": 5.0, "yaw": 10.0, "roll": 0.0})
        
        assert "status" in result
        assert rcs.control_mode == "rate"
        assert rcs.angular_velocity_target["pitch"] == 5.0
        assert rcs.angular_velocity_target["yaw"] == 10.0
    
    def test_rcs_tick_updates_angular_velocity(self):
        """Test that RCS tick applies torque to update angular velocity."""
        rcs = RCSSystem({})
        ship = MockShip()
        event_bus = MockEventBus()
        
        # Set a yaw rate target
        rcs.set_angular_velocity_target({"pitch": 0, "yaw": 10.0, "roll": 0})
        
        # Run several ticks
        dt = 0.1
        for _ in range(10):
            rcs.tick(dt, ship, event_bus)
        
        # Angular velocity should have increased toward target
        # (may not reach target due to controller dynamics)
        assert abs(ship.angular_velocity["yaw"]) > 0.1  # Some rotation occurred
    
    def test_clear_target(self):
        """Test clearing all targets."""
        rcs = RCSSystem({})
        
        rcs.set_attitude_target({"pitch": 30, "yaw": 45, "roll": 0})
        assert rcs.attitude_target is not None
        
        result = rcs.clear_target()
        
        assert rcs.attitude_target is None
        assert rcs.angular_velocity_target == {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        assert rcs.control_mode == "rate"
    
    def test_rcs_get_state(self):
        """Test RCS state reporting."""
        rcs = RCSSystem({})
        rcs.set_attitude_target({"pitch": 10, "yaw": 20, "roll": 0})
        
        state = rcs.get_state()
        
        assert "status" in state
        assert "control_mode" in state
        assert "attitude_target" in state
        assert "thruster_count" in state
        assert state["control_mode"] == "attitude"
        assert state["attitude_target"]["pitch"] == 10


class TestRCSIntegration:
    """Integration tests for RCS with ship physics."""
    
    def test_attitude_control_convergence(self):
        """Test that RCS can rotate ship toward target attitude."""
        rcs = RCSSystem({"attitude_kp": 3.0, "attitude_kd": 2.0})
        ship = MockShip()
        event_bus = MockEventBus()
        ship.systems["rcs"] = rcs
        
        # Set target attitude
        target_yaw = 45.0
        rcs.set_attitude_target({"pitch": 0, "yaw": target_yaw, "roll": 0})
        
        # Run simulation for several seconds
        dt = 0.1
        for _ in range(100):  # 10 seconds
            rcs.tick(dt, ship, event_bus)
            
            # Simple physics integration (normally done by Ship._update_physics)
            ship.orientation["pitch"] += ship.angular_velocity["pitch"] * dt
            ship.orientation["yaw"] += ship.angular_velocity["yaw"] * dt
            ship.orientation["roll"] += ship.angular_velocity["roll"] * dt
        
        # Should have converged toward target
        # Allow some tolerance due to control dynamics
        yaw_error = abs(ship.orientation["yaw"] - target_yaw)
        assert yaw_error < 15.0, f"Yaw error {yaw_error} too large (target: {target_yaw})"
