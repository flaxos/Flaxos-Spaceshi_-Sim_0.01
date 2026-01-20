# hybrid/systems/weapons/weapon_system.py

import time
from hybrid.core.constants import DEFAULT_COOLDOWN_TIME, DEFAULT_WEAPON_HEAT_INCREMENT
from hybrid.core.event_bus import EventBus

class Weapon:
    def __init__(self, name, power_cost, max_heat, ammo_count=None, damage=10.0):
        self.name = name
        self.power_cost = power_cost
        self.max_heat = max_heat
        self.ammo = ammo_count
        self.damage = damage  # D6: Damage per hit
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

    def fire(self, current_time, power_manager, target_ship=None):
        """Fire weapon at target.

        Args:
            current_time: Current time
            power_manager: Power management system
            target_ship: Target Ship object (optional, for damage application)

        Returns:
            dict: Fire result with damage info
        """
        if not self.can_fire(current_time):
            self.event_bus.publish("weapon_cannot_fire", {"weapon": self.name})
            return {"ok": False, "reason": "cannot_fire"}
        if not power_manager.request_power(self.power_cost, "weapon"):
            return {"ok": False, "reason": "insufficient_power"}

        self.heat += DEFAULT_WEAPON_HEAT_INCREMENT
        self.last_fired = current_time
        if self.ammo is not None:
            self.ammo -= 1

        # D6: Apply damage to target if provided
        damage_result = None
        if target_ship and hasattr(target_ship, 'take_damage'):
            damage_result = target_ship.take_damage(self.damage, source=self.name)

        # Extract target ID (handle both Ship objects and string IDs)
        target_id = None
        if target_ship:
            if hasattr(target_ship, 'id'):
                target_id = target_ship.id
            else:
                target_id = target_ship  # Assume it's already a string ID

        self.event_bus.publish("weapon_fired", {
            "weapon": self.name,
            "target": target_id,
            "damage": self.damage,
            "damage_result": damage_result
        })

        return {
            "ok": True,
            "damage": self.damage,
            "target": target_id,
            "damage_result": damage_result
        }

    def cool_down(self, dt):
        # Passive cooldown proportional to max_heat
        self.heat = max(0.0, self.heat - dt * (self.max_heat / 10))

class WeaponSystem:
    def __init__(self, config):
        # config is a dict with a "weapons" list of dicts
        self.weapons = {}
        for wcfg in config.get("weapons", []):
            weapon = Weapon(
                name=wcfg["name"],
                power_cost=wcfg["power_cost"],
                max_heat=wcfg["max_heat"],
                ammo_count=wcfg.get("ammo"),
                damage=wcfg.get("damage", 10.0)  # D6: Default 10 damage if not specified
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

            # D6: Resolve target ship for damage application
            target_id = params.get("target")
            target_ship = None

            # If no explicit target, try to get locked target from targeting system
            if not target_id:
                targeting = ship.systems.get("targeting")
                if targeting and hasattr(targeting, "locked_target"):
                    target_id = targeting.locked_target

            # Resolve target ID to ship object
            if target_id:
                all_ships = params.get("all_ships", {})
                target_ship = all_ships.get(target_id)
                if not target_ship:
                    # Target ID provided but not found
                    return {"error": f"Target '{target_id}' not found"}

            # Fire the weapon
            current_time = time.time()
            fire_result = weapon.fire(current_time, power_manager, target_ship)

            if fire_result.get("ok"):
                return {
                    "ok": True,
                    "message": f"Weapon '{weapon_name}' fired",
                    "weapon": weapon_name,
                    "target": target_id,
                    "heat": weapon.heat,
                    "ammo_remaining": weapon.ammo,
                    "damage": fire_result.get("damage"),
                    "damage_result": fire_result.get("damage_result"),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%f")
                }
            else:
                reason = fire_result.get("reason", "unknown")
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
