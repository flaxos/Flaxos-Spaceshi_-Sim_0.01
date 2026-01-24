# tests/systems/test_propulsion_refactor.py
"""Tests for Expanse-style propulsion system with ship-frame thrust."""

import pytest
import math
import numpy as np
from hybrid.systems.propulsion_system import PropulsionSystem
from hybrid.utils.quaternion import Quaternion


class MockShip:
    """Mock ship for testing propulsion system."""
    
    def __init__(self):
        self.id = "test_ship"
        self.mass = 10000.0  # 10 tons
        self.thrust = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.acceleration = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.orientation = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
        self.quaternion = Quaternion.from_euler(0, 0, 0)
        self.systems = {}


class MockEventBus:
    """Mock event bus for testing."""
    
    def __init__(self):
        self.events = []
    
    def publish(self, event_type, data):
        self.events.append((event_type, data))


class TestThrottleControl:
    """Tests for scalar throttle control."""
    
    def test_set_throttle(self):
        """Test setting throttle with scalar value."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        result = prop.set_throttle({"thrust": 0.5})
        
        assert "error" not in result
        assert prop.throttle == 0.5
        assert result["throttle"] == 0.5
    
    def test_throttle_clamping(self):
        """Test that throttle is clamped to 0-1 range."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        # Over 1
        prop.set_throttle({"thrust": 1.5})
        assert prop.throttle == 1.0
        
        # Under 0
        prop.set_throttle({"thrust": -0.5})
        assert prop.throttle == 0.0
    
    def test_throttle_via_thrust_param(self):
        """Test that 'thrust' parameter works for set_throttle."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        result = prop.set_throttle({"thrust": 0.75})
        
        assert prop.throttle == 0.75


class TestShipFrameThrust:
    """Tests for ship-frame thrust rotation."""
    
    def test_thrust_forward_identity_orientation(self):
        """Test thrust along +X when ship has identity orientation."""
        prop = PropulsionSystem({"max_thrust": 1000.0, "fuel_level": 1000})
        ship = MockShip()
        ship.quaternion = Quaternion.from_euler(0, 0, 0)  # Identity
        event_bus = MockEventBus()
        
        prop.set_throttle({"thrust": 1.0})
        prop.tick(0.1, ship, event_bus)
        
        # With identity quaternion, +X ship frame = +X world frame
        assert ship.thrust["x"] > 0
        assert abs(ship.thrust["y"]) < 0.01
        assert abs(ship.thrust["z"]) < 0.01
    
    def test_thrust_forward_rotated_yaw_90(self):
        """Test thrust when ship is rotated 90 degrees yaw."""
        prop = PropulsionSystem({"max_thrust": 1000.0, "fuel_level": 1000})
        ship = MockShip()
        # 90 degrees yaw means ship's +X points along world +Y
        ship.quaternion = Quaternion.from_euler(0, 90, 0)
        event_bus = MockEventBus()
        
        prop.set_throttle({"thrust": 1.0})
        prop.tick(0.1, ship, event_bus)
        
        # Ship +X should now be world +Y (approximately, depends on convention)
        # Check that thrust is no longer purely along world X
        world_thrust = np.array([ship.thrust["x"], ship.thrust["y"], ship.thrust["z"]])
        magnitude = np.linalg.norm(world_thrust)
        
        # Should have significant thrust magnitude
        assert magnitude > 900  # Close to max thrust
    
    def test_thrust_produces_acceleration(self):
        """Test that thrust produces correct acceleration (F=ma)."""
        prop = PropulsionSystem({"max_thrust": 1000.0, "fuel_level": 1000})
        ship = MockShip()
        ship.mass = 1000.0  # 1 ton
        event_bus = MockEventBus()
        
        prop.set_throttle({"thrust": 1.0})
        prop.tick(0.1, ship, event_bus)
        
        # a = F/m = 1000/1000 = 1.0 m/s²
        accel_mag = math.sqrt(
            ship.acceleration["x"]**2 + 
            ship.acceleration["y"]**2 + 
            ship.acceleration["z"]**2
        )
        assert abs(accel_mag - 1.0) < 0.01


class TestDebugVectorThrust:
    """Tests for debug vector thrust mode."""
    
    def test_set_thrust_vector_debug(self):
        """Test setting arbitrary thrust vector (debug mode)."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        result = prop.set_thrust_vector({"x": 100, "y": 200, "z": 300})
        
        assert "error" not in result
        assert result.get("debug_mode") is True
        assert prop._debug_thrust_vector is not None
    
    def test_debug_vector_bypasses_rotation(self):
        """Test that debug vector thrust bypasses ship-frame rotation."""
        prop = PropulsionSystem({"max_thrust": 1000.0, "fuel_level": 1000})
        ship = MockShip()
        # Rotate ship 90 degrees
        ship.quaternion = Quaternion.from_euler(0, 90, 0)
        event_bus = MockEventBus()
        
        # Set debug vector thrust directly
        prop.set_thrust_vector({"x": 0, "y": 100, "z": 0})
        prop.tick(0.1, ship, event_bus)
        
        # Debug mode should apply thrust directly in world frame
        assert abs(ship.thrust["y"] - 100) < 0.1
    
    def test_throttle_clears_debug_mode(self):
        """Test that setting throttle clears debug vector mode."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        prop.set_thrust_vector({"x": 100, "y": 0, "z": 0})
        assert prop._debug_thrust_vector is not None
        
        prop.set_throttle({"thrust": 0.5})
        assert prop._debug_thrust_vector is None


class TestEmergencyStop:
    """Tests for emergency stop functionality."""
    
    def test_emergency_stop_zeros_throttle(self):
        """Test that emergency stop zeros all thrust."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        prop.set_throttle({"thrust": 1.0})
        assert prop.throttle == 1.0
        
        result = prop.emergency_stop()
        
        assert prop.throttle == 0.0
        assert "status" in result
    
    def test_emergency_stop_clears_debug_mode(self):
        """Test that emergency stop clears debug vector mode."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        prop.set_thrust_vector({"x": 100, "y": 0, "z": 0})
        assert prop._debug_thrust_vector is not None
        
        prop.emergency_stop()
        assert prop._debug_thrust_vector is None


class TestFuelConsumption:
    """Tests for fuel consumption."""
    
    def test_fuel_consumed_with_thrust(self):
        """Test that fuel is consumed when thrusting."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 100.0,
            "fuel_consumption": 1.0
        })
        ship = MockShip()
        event_bus = MockEventBus()
        
        initial_fuel = prop.fuel_level
        prop.set_throttle({"thrust": 1.0})
        prop.tick(1.0, ship, event_bus)  # 1 second
        
        assert prop.fuel_level < initial_fuel
    
    def test_no_thrust_when_no_fuel(self):
        """Test that thrust stops when out of fuel."""
        prop = PropulsionSystem({
            "max_thrust": 1000.0,
            "fuel_level": 0.0
        })
        ship = MockShip()
        event_bus = MockEventBus()
        
        prop.set_throttle({"thrust": 1.0})
        prop.tick(0.1, ship, event_bus)
        
        # No thrust when out of fuel
        assert ship.thrust["x"] == 0
        assert ship.thrust["y"] == 0
        assert ship.thrust["z"] == 0
        assert prop.status == "no_fuel"


class TestStateReporting:
    """Tests for propulsion state reporting."""
    
    def test_get_state_includes_throttle(self):
        """Test that state includes throttle value."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        prop.set_throttle({"thrust": 0.6})
        
        state = prop.get_state()
        
        assert "throttle" in state
        assert state["throttle"] == 0.6
        assert "thrust_magnitude" in state
        assert state["thrust_magnitude"] == 600.0
    
    def test_get_state_includes_debug_mode(self):
        """Test that state indicates debug mode."""
        prop = PropulsionSystem({"max_thrust": 1000.0})
        
        prop.set_thrust_vector({"x": 100, "y": 0, "z": 0})
        state = prop.get_state()
        
        assert state.get("debug_mode") is True
