# hybrid/systems/weapons/weapon_system.py
"""Legacy weapon system providing basic weapon management.

The newer TruthWeapon system in truth_weapons.py provides physics-based
ballistics. This module is retained for backward compatibility and simpler
weapon configurations.
"""

import time
from typing import Dict, List, Optional
from hybrid.core.constants import DEFAULT_COOLDOWN_TIME, DEFAULT_WEAPON_HEAT_INCREMENT
from hybrid.core.event_bus import EventBus


class Weapon:
    """A single weapon instance with heat, ammo, and cooldown tracking."""

    def __init__(
        self,
        name: str,
        power_cost: float,
        max_heat: float,
        ammo_count: Optional[int] = None,
        damage: float = 10.0,
    ) -> None:
        """Initialize a weapon.

        Args:
            name: Display name of the weapon.
            power_cost: Power units consumed per shot.
            max_heat: Maximum heat capacity before lockout.
            ammo_count: Ammunition capacity (None for unlimited).
            damage: Base damage per hit.
        """
        self.name: str = name
        self.power_cost: float = power_cost
        self.base_power_cost: float = power_cost
        self.max_heat: float = max_heat
        self.base_max_heat: float = max_heat
        self.enabled: bool = True
        self.ammo: Optional[int] = ammo_count
        self.ammo_capacity: Optional[int] = ammo_count
        self.damage: float = damage
        self.base_damage: float = damage
        self.heat: float = 0.0
        self.last_fired: float = 0.0
        self.cooldown_time: float = DEFAULT_COOLDOWN_TIME
        self.event_bus: EventBus = EventBus.get_instance()

    def can_fire(self, current_time: float) -> bool:
        """Check whether the weapon can fire right now.

        Args:
            current_time: Current simulation or wall-clock time.

        Returns:
            True if the weapon is enabled, cooled down, under heat cap,
            and has ammunition.
        """
        return (
            self.enabled
            and (current_time - self.last_fired) >= self.cooldown_time
            and self.heat < self.max_heat
            and (self.ammo is None or self.ammo > 0)
        )

    def fire(
        self,
        current_time: float,
        power_manager,
        target_ship=None,
        ship_id: Optional[str] = None,
        damage_factor: float = 1.0,
        damage_model=None,
        event_bus=None,
        target_subsystem: Optional[str] = None,
    ) -> dict:
        """Fire weapon at target.

        Args:
            current_time: Current time.
            power_manager: Power management system for power draw.
            target_ship: Target Ship object (optional, for damage application).
            ship_id: ID of the firing ship.
            damage_factor: Weapon degradation multiplier (0-1).
            damage_model: DamageModel for heat reporting.
            event_bus: EventBus for publishing events.
            target_subsystem: Specific subsystem to target on the target ship.

        Returns:
            dict: Fire result with damage info.
        """
        if damage_factor <= 0.0:
            self.event_bus.publish("weapon_cannot_fire", {"weapon": self.name, "reason": "damaged"})
            return {"ok": False, "reason": "damaged"}
        if not self.enabled:
            self.event_bus.publish("weapon_cannot_fire", {"weapon": self.name, "reason": "disabled"})
            return {"ok": False, "reason": "disabled"}
        if not self.can_fire(current_time):
            self.event_bus.publish("weapon_cannot_fire", {"weapon": self.name})
            return {"ok": False, "reason": "cannot_fire"}
        if not power_manager.request_power(self.power_cost, "weapon"):
            return {"ok": False, "reason": "insufficient_power"}

        self.heat += DEFAULT_WEAPON_HEAT_INCREMENT
        self.last_fired = current_time
        if self.ammo is not None:
            self.ammo -= 1
        if damage_model is not None:
            heat_amount = max(0.0, self.power_cost)
            if heat_amount > 0:
                damage_model.add_heat("weapons", heat_amount, event_bus, ship_id)

        # D6: Apply damage to target if provided
        damage_result = None
        effective_damage = self.damage * damage_factor
        if target_ship and hasattr(target_ship, 'take_damage'):
            damage_result = target_ship.take_damage(
                effective_damage,
                source=self.name,
                target_subsystem=target_subsystem,
            )

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
            "damage": effective_damage,
            "damage_result": damage_result,
            "ship_id": ship_id,
        })

        return {
            "ok": True,
            "damage": effective_damage,
            "target": target_id,
            "damage_result": damage_result
        }

    def cool_down(self, dt: float) -> None:
        """Passively cool the weapon over time.

        Args:
            dt: Time delta in seconds.
        """
        self.heat = max(0.0, self.heat - dt * (self.max_heat / 10))

    def resupply(self) -> dict:
        """Resupply ammunition to full capacity.

        Returns:
            dict: Resupply result including previous and new ammo counts.
        """
        if self.ammo_capacity is None:
            return {"ok": False, "reason": "no_ammo", "weapon": self.name}
        previous = self.ammo
        self.ammo = self.ammo_capacity
        return {
            "ok": True,
            "weapon": self.name,
            "previous_ammo": previous,
            "ammo": self.ammo,
            "capacity": self.ammo_capacity,
        }


class WeaponSystem:
    """Manages a collection of legacy Weapon instances on a ship."""

    def __init__(self, config: dict) -> None:
        """Initialize weapon system from configuration.

        Args:
            config: Dict with a ``weapons`` key containing a list of weapon
                configuration dicts (each with name, power_cost, max_heat, etc.).
        """
        self.weapons: Dict[str, Weapon] = {}
        for wcfg in config.get("weapons", []):
            weapon = Weapon(
                name=wcfg["name"],
                power_cost=wcfg["power_cost"],
                max_heat=wcfg["max_heat"],
                ammo_count=wcfg.get("ammo"),
                damage=wcfg.get("damage", 10.0)
            )
            self.weapons[wcfg["name"]] = weapon
        self.event_bus: EventBus = EventBus.get_instance()
        self.damage_factor: float = 1.0

    def tick(self, dt, ship=None, event_bus=None):
        """Update weapon system.

        Args:
            dt: Time delta
            ship: Ship with this weapon system (optional)
            event_bus: Event bus (optional)
        """
        if ship is not None and hasattr(ship, "get_effective_factor"):
            self.damage_factor = ship.get_effective_factor("weapons")
        elif ship is not None and hasattr(ship, "damage_model"):
            self.damage_factor = ship.damage_model.get_combined_factor("weapons")
        else:
            self.damage_factor = 1.0

        for weapon in self.weapons.values():
            weapon.max_heat = weapon.base_max_heat * max(0.25, self.damage_factor)
            weapon.power_cost = weapon.base_power_cost * (1.0 + (1.0 - self.damage_factor))
            weapon.damage = weapon.base_damage * max(0.1, self.damage_factor)

        for weapon in self.weapons.values():
            weapon.cool_down(dt)

    def resupply(self) -> dict:
        """Resupply all weapons.

        Returns:
            dict: Per-weapon resupply results.
        """
        results = []
        for weapon in self.weapons.values():
            results.append(weapon.resupply())
        return {
            "ok": True,
            "weapons": results,
        }

    def fire_weapon(
        self,
        weapon_name: str,
        power_manager,
        target,
        ship=None,
        target_subsystem: Optional[str] = None,
    ) -> dict:
        """Fire a named weapon.

        Args:
            weapon_name: Name of the weapon to fire.
            power_manager: Power system for power draw.
            target: Target ship object or ID.
            ship: Firing ship (for damage model / event context).
            target_subsystem: Specific subsystem to target.

        Returns:
            dict: Fire result, or False if weapon not found.
        """
        weapon = self.weapons.get(weapon_name)
        if not weapon:
            return False
        current_time = time.time()
        damage_model = ship.damage_model if ship is not None and hasattr(ship, "damage_model") else None
        event_bus = ship.event_bus if ship is not None and hasattr(ship, "event_bus") else None
        ship_id = ship.id if ship is not None and hasattr(ship, "id") else None
        return weapon.fire(
            current_time,
            power_manager,
            target,
            ship_id=ship_id,
            damage_factor=self.damage_factor,
            damage_model=damage_model,
            event_bus=event_bus,
            target_subsystem=target_subsystem,
        )

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
                    "enabled": w.enabled,
                    "can_fire": w.can_fire(time.time())
                }
                for w in self.weapons.values()
            ],
            "status": "failed" if self.damage_factor <= 0.0 else "degraded" if self.damage_factor < 1.0 else "online",
            "degradation_factor": self.damage_factor,
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
            target_subsystem = params.get("target_subsystem")

            # If no explicit target, try to get locked target from targeting system
            if not target_id:
                targeting = ship.systems.get("targeting")
                if targeting and hasattr(targeting, "locked_target"):
                    target_id = targeting.locked_target
            if target_subsystem is None:
                targeting = ship.systems.get("targeting")
                if targeting and hasattr(targeting, "target_subsystem"):
                    target_subsystem = targeting.target_subsystem

            # Resolve target ID to ship object
            if target_id:
                all_ships = params.get("all_ships", {})
                target_ship = all_ships.get(target_id)
                if not target_ship:
                    # Target ID provided but not found
                    return {"error": f"Target '{target_id}' not found"}

            # Fire the weapon
            current_time = time.time()
            fire_result = weapon.fire(
                current_time,
                power_manager,
                target_ship,
                ship_id=ship.id,
                damage_factor=self.damage_factor,
                damage_model=ship.damage_model if hasattr(ship, "damage_model") else None,
                event_bus=ship.event_bus if hasattr(ship, "event_bus") else None,
                target_subsystem=target_subsystem,
            )

            if fire_result.get("ok"):
                return {
                    "ok": True,
                    "message": f"Weapon '{weapon_name}' fired",
                    "weapon": weapon_name,
                    "target": target_id,
                    "target_subsystem": target_subsystem,
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
