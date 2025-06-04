# hybrid/systems/weapons/hardpoint.py
from dataclasses import dataclass
from typing import Optional
import time
from hybrid.systems.weapons.weapon_system import Weapon

@dataclass
class Hardpoint:
    id: str
    mount_type: str  # "turret", "fixed", "missile_rack", etc.
    weapon: Optional[Weapon] = None

    def mount_weapon(self, weapon):
        if self.weapon is None and weapon:
            self.weapon = weapon
            return True
        return False

    def unmount_weapon(self):
        if self.weapon:
            self.weapon = None
            return True
        return False

    def fire(self, power_manager, target):
        if self.weapon:
            return self.weapon.fire(time.time(), power_manager, target)
        return False
