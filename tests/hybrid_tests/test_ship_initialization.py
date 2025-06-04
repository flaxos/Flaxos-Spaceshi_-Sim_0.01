import unittest
from hybrid.ship import Ship

class TestShipInitialization(unittest.TestCase):
    def test_init_defaults(self):
        ship = Ship('s1', {})
        self.assertEqual(ship.id, 's1')
        self.assertTrue('systems' in ship.get_state())

if __name__ == '__main__':
    unittest.main()
