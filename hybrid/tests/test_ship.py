# hybrid/tests/test_ship.py
"""
Tests for the Ship class in the hybrid architecture.
"""

import unittest
from hybrid.ship import Ship
from hybrid.core.event_bus import EventBus

class TestShip(unittest.TestCase):
    """
    Test cases for the Ship class
    """
    
    def test_ship_initialization(self):
        """Test basic ship initialization"""
        config = {
            "position": {"x": 10.0, "y": 20.0, "z": 30.0},
            "velocity": {"x": 1.0, "y": 2.0, "z": 3.0},
            "orientation": {"pitch": 45.0, "yaw": 90.0, "roll": 0.0},
            "mass": 1000.0
        }
        
        ship = Ship("test_ship_001", config)
        
        self.assertEqual(ship.id, "test_ship_001")
        self.assertEqual(ship.position["x"], 10.0)
        self.assertEqual(ship.velocity["y"], 2.0)
        self.assertEqual(ship.orientation["yaw"], 90.0)
        self.assertEqual(ship.mass, 1000.0)
        
    def test_ship_physics(self):
        """Test basic physics updates"""
        ship = Ship("test_ship_001", {"mass": 100.0})
        
        # Apply force and tick
        force = {"x": 100.0, "y": 0.0, "z": 0.0}
        dt = 1.0
        
        # Manually call the physics update
        ship._update_physics(dt, force)
        
        # Check acceleration (F = ma)
        self.assertEqual(ship.acceleration["x"], 1.0)  # 100 / 100
        
        # Check velocity (v = v0 + a*t)
        self.assertEqual(ship.velocity["x"], 1.0)  # 0 + 1*1
        
        # Check position (p = p0 + v*t)
        self.assertEqual(ship.position["x"], 1.0)  # 0 + 1*1

    def test_ship_command(self):
        """Test ship command handling"""
        ship = Ship("test_ship_001", {})
        
        # Test get_position command
        response = ship.command("get_position", {})
        self.assertEqual(response["x"], 0.0)
        
        # Test get_state command
        response = ship.command("get_state", {})
        self.assertEqual(response["id"], "test_ship_001")
        self.assertTrue("systems" in response)

if __name__ == '__main__':
    unittest.main()
