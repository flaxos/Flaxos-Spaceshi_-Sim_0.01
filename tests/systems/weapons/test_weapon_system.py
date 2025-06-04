import unittest
from hybrid.systems.weapons.weapon_system import WeaponSystem
from hybrid.systems.power.management import PowerManagementSystem

class TestWeaponSystem(unittest.TestCase):
    def setUp(self):
        wcfg = {
            'weapons': [
                {'name': 'laser', 'power_cost': 5, 'max_heat': 20, 'ammo': None}
            ]
        }
        self.weapons = WeaponSystem(wcfg)
        self.power = PowerManagementSystem({'primary': {'capacity': 50}})
        self.power.tick(1.0)

    def test_fire_weapon(self):
        fired = self.weapons.fire_weapon('laser', self.power, 'target1')
        self.assertTrue(fired)
        weapon = self.weapons.weapons['laser']
        self.assertGreater(weapon.heat, 0)

    def test_cooldown(self):
        weapon = self.weapons.weapons['laser']
        weapon.fire(0, self.power, 't')
        weapon.cool_down(1.0)
        self.assertLess(weapon.heat, 5)

if __name__ == '__main__':
    unittest.main()

from hybrid.systems.weapons.hardpoint import Hardpoint

class TestHardpoint(unittest.TestCase):
    def test_mount_fire(self):
        wcfg = {
            'weapons': [
                {'name': 'laser', 'power_cost': 5, 'max_heat': 20, 'ammo': 2}
            ]
        }
        weapons = WeaponSystem(wcfg)
        power = PowerManagementSystem({'primary': {'capacity': 50}})
        power.tick(1.0)
        hp = Hardpoint(id='hp1', mount_type='fixed')
        hp.mount_weapon(weapons.weapons['laser'])
        fired = hp.fire(power, 't')
        self.assertTrue(fired)
        self.assertEqual(weapons.weapons['laser'].ammo, 1)
