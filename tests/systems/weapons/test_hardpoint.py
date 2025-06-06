# tests/systems/weapons/test_hardpoint.py

from hybrid.systems.weapons.hardpoint import Hardpoint
from hybrid.systems.weapons.weapon_system import Weapon


def test_hardpoint_mount_and_fire():
    hp = Hardpoint(id="hp1", mount_type="turret")
    w = Weapon(name="cannon", power_cost=1.0, max_heat=10.0)
    assert hp.mount_weapon(w)
    assert hp.weapon is w
    assert hp.unmount_weapon()
    assert hp.weapon is None
