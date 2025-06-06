# tests/systems/weapons/test_weapon_system.py

import time
import pytest
from hybrid.systems.power.management import PowerManagementSystem
from hybrid.systems.weapons.weapon_system import WeaponSystem


def test_weapon_firing_and_cooldown():
    config = {"primary": {}, "secondary": {}, "tertiary": {}}
    pm = PowerManagementSystem(config)
    pm.reactors["primary"].available = 100.0

    wcfg = {"name": "laser", "power_cost": 10.0, "max_heat": 50.0, "ammo": 3}
    wep_sys = WeaponSystem({"weapons": [wcfg]})
    weapon = wep_sys.weapons["laser"]

    current_time = time.time()
    # First shot should succeed
    fired = weapon.fire(current_time, pm, "target_dummy")
    assert fired
    assert weapon.ammo == 2
    assert weapon.heat == pytest.approx(5.0)

    # Immediately try to fire again: should fail due to cooldown
    fired2 = weapon.fire(current_time, pm, "target_dummy")
    assert not fired2

    # Advance time and cool down
    weapon.cool_down(10.0)
    assert weapon.heat < 5.0
