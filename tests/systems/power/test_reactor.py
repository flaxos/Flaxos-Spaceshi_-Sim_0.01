import unittest
from hybrid.systems.power.reactor import Reactor
from hybrid.core.constants import DEFAULT_REACTOR_OUTPUT

class TestReactor(unittest.TestCase):
    def test_tick_ramp_and_overheat(self):
        r = Reactor('primary', capacity=50, output_rate=10, thermal_limit=30)
        r.tick(1.0)
        self.assertAlmostEqual(r.available, 10)
        r.temperature = 35
        r.tick(1.0)
        self.assertEqual(r.status, 'overheated')
        self.assertLess(r.available, 20)

if __name__ == '__main__':
    unittest.main()
