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

    def tick(self, dt, ship=None, event_bus=None):
        """Update weapon system.

        Args:
            dt: Time delta
            ship: Ship with this weapon system (optional)
            event_bus: Event bus (optional)
        """
        for weapon in self.weapons.values():
            weapon.cool_down(dt)

    def fire_weapon(self, weapon_name, power_manager, target):
        weapon = self.weapons.get(weapon_name)
        if not weapon:
            return False
        current_time = time.time()
        return weapon.fire(current_time, power_manager, target)

    def get_state(self):
        """Get weapon system state.

        Returns:
            dict: Weapon system state
        """
        return {
            "enabled": True,
            "weapons": [
                {
                    "name": w.name,
                    "heat": w.heat,
                    "max_heat": w.max_heat,
                    "ammo": w.ammo,
                    "can_fire": w.can_fire(time.time())
                }
                for w in self.weapons.values()
            ]
        }

    def command(self, action: str, params: dict):
        """Handle weapon commands.

        Args:
            action: Command action
            params: Parameters

        Returns:
            dict: Result
        """
        if action == "fire":
            weapon_name = params.get("weapon")
            if not weapon_name:
                return {"error": "Missing weapon parameter"}

            weapon = self.weapons.get(weapon_name)
            if not weapon:
                return {"error": f"Weapon '{weapon_name}' not found"}

            # Get ship from params for power manager
            ship = params.get("ship")
            if not ship:
                return {"error": "Ship reference required"}

            # Get power manager from ship
            power_manager = ship.systems.get("power") or ship.systems.get("power_management")
            if not power_manager:
                return {"error": "Power system not available"}

            # Get target (optional)
            target = params.get("target")

            # Fire the weapon
            current_time = time.time()
            if weapon.fire(current_time, power_manager, target):
                return {
                    "ok": True,
                    "message": f"Weapon '{weapon_name}' fired",
                    "weapon": weapon_name,
                    "target": target,
                    "heat": weapon.heat,
                    "ammo_remaining": weapon.ammo
                }
            else:
                reason = "unknown"
                if weapon.heat >= weapon.max_heat:
                    reason = "overheated"
                elif weapon.ammo is not None and weapon.ammo <= 0:
                    reason = "out of ammo"
                elif (current_time - weapon.last_fired) < weapon.cooldown_time:
                    reason = "still cooling down"
                return {
                    "error": f"Weapon cannot fire: {reason}",
                    "heat": weapon.heat,
                    "cooldown_remaining": max(0, weapon.cooldown_time - (current_time - weapon.last_fired))
                }

        return {"error": f"Unknown weapon command: {action}"}
