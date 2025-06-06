# hybrid/systems/weapons/weapon_system.py

import time
from hybrid.core.constants import DEFAULT_COOLDOWN_TIME, DEFAULT_WEAPON_HEAT_INCREMENT
from hybrid.core.event_bus import EventBus

class Weapon:
    def __init__(self, name, power_cost, max_heat, ammo_count=None):
        self.name = name
        self.power_cost = power_cost
        self.max_heat = max_heat
        self.ammo = ammo_count
        self.heat = 0.0
        self.last_fired = 0.0
        self.cooldown_time = DEFAULT_COOLDOWN_TIME
        self.event_bus = EventBus.get_instance()

    def can_fire(self, current_time):
        return (
            (current_time - self.last_fired) >= self.cooldown_time
            and self.heat < self.max_heat
            and (self.ammo is None or self.ammo > 0)
        )

    def fire(self, current_time, power_manager, target):
        if not self.can_fire(current_time):
            self.event_bus.publish("weapon_cannot_fire", {"weapon": self.name})
            return False
        if not power_manager.request_power(self.power_cost, "weapon"):
            return False
        self.heat += DEFAULT_WEAPON_HEAT_INCREMENT
        self.last_fired = current_time
        if self.ammo is not None:
            self.ammo -= 1
        self.event_bus.publish("weapon_fired", {"weapon": self.name, "target": target})
        return True

    def cool_down(self, dt):
        # Passive cooldown proportional to max_heat
        self.heat = max(0.0, self.heat - dt * (self.max_heat / 10))

class WeaponSystem:
    def __init__(self, config):
        # config is a dict with a “weapons” list of dicts
        self.weapons = {}
        for wcfg in config.get("weapons", []):
            weapon = Weapon(
                name=wcfg["name"],
                power_cost=wcfg["power_cost"],
                max_heat=wcfg["max_heat"],
                ammo_count=wcfg.get("ammo")
            )
            self.weapons[wcfg["name"]] = weapon
        self.event_bus = EventBus.get_instance()

    def tick(self, dt):
        for weapon in self.weapons.values():
            weapon.cool_down(dt)

    def fire_weapon(self, weapon_name, power_manager, target):
        weapon = self.weapons.get(weapon_name)
        if not weapon:
            return False
        current_time = time.time()
        return weapon.fire(current_time, power_manager, target)
