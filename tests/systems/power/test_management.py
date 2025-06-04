import unittest
from hybrid.systems.power.management import PowerManagementSystem

class TestPowerManagement(unittest.TestCase):
    def test_request_power_priority(self):
        cfg = {
            'primary': {'capacity': 50},
            'secondary': {'capacity': 30},
        }
        pm = PowerManagementSystem(cfg)
        pm.tick(1.0)
        success = pm.request_power(5, 'weapons')
        self.assertTrue(success)
        self.assertLess(pm.reactors['primary'].available, 50)

if __name__ == '__main__':
    unittest.main()
