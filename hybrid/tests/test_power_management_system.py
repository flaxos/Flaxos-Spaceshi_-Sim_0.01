import unittest
from hybrid.systems.power_management_system import PowerManagementSystem

class TestPowerManagementSystem(unittest.TestCase):
    def setUp(self):
        self.pm = PowerManagementSystem({
            "primary": {"output": 100},
            "secondary": {"output": 50},
            "tertiary": {"output": 30},
        })
        self.pm.tick(1.0, None, None)

    def test_basic_allocation(self):
        self.assertTrue(self.pm.request_power(60, "propulsion"))
        state = self.pm.get_state()
        self.assertAlmostEqual(state["primary"]["available"], 40)

    def test_overload(self):
        success = self.pm.request_power(200, "propulsion")
        self.assertFalse(success)

    def test_reroute(self):
        moved = self.pm.reroute_power(20, "primary", "secondary")
        self.assertEqual(moved, 20)
        state = self.pm.get_state()
        self.assertAlmostEqual(state["primary"]["available"], 80)
        self.assertAlmostEqual(state["secondary"]["available"], 70)

if __name__ == "__main__":
    unittest.main()

