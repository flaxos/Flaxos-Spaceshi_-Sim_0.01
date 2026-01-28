# hybrid/systems/combat/combat_system.py
"""Combat system for coordinating weapons, targeting, and damage.

Sprint C: Combat loop v1 implementation.
Integrates truth weapons with targeting pipeline.
"""

import logging
from typing import Dict, List, Optional
from hybrid.core.base_system import BaseSystem
from hybrid.core.event_bus import EventBus
from hybrid.utils.errors import success_dict, error_dict
from hybrid.systems.weapons.truth_weapons import (
    TruthWeapon, create_railgun, create_pdc,
    RAILGUN_SPECS, PDC_SPECS, WeaponSpecs
)

logger = logging.getLogger(__name__)


class CombatSystem(BaseSystem):
    """Combat system managing weapons and engagement.

    Provides:
    - Truth weapon management (railgun, PDC)
    - Weapon firing coordination
    - Combat state tracking
    - Integration with targeting system
    """

    def __init__(self, config: dict):
        """Initialize combat system.

        Args:
            config: Configuration dict with:
                - railguns: Number of railgun mounts (default 1)
                - pdcs: Number of PDC mounts (default 2)
                - weapons: List of custom weapon configs
        """
        super().__init__(config)

        # Initialize truth weapons
        self.truth_weapons: Dict[str, TruthWeapon] = {}

        # Create railguns
        num_railguns = config.get("railguns", config.get("railgun_mounts", 1))
        for i in range(num_railguns):
            mount_id = f"railgun_{i+1}"
            self.truth_weapons[mount_id] = create_railgun(mount_id)

        # Create PDCs
        num_pdcs = config.get("pdcs", config.get("pdc_turrets", 2))
        for i in range(num_pdcs):
            mount_id = f"pdc_{i+1}"
            self.truth_weapons[mount_id] = create_pdc(mount_id)

        # Combat state
        self.engaging = False
        self.shots_fired = 0
        self.hits = 0
        self.damage_dealt = 0.0

        # Damage tracking
        self._damage_factor = 1.0

        # Ship reference
        self._ship_ref = None
        self._sim_time = 0.0

        # Event bus
        self.event_bus = EventBus.get_instance()

    def tick(self, dt: float, ship, event_bus):
        """Update combat system each tick.

        Args:
            dt: Time delta
            ship: Ship with this combat system
            event_bus: Event bus
        """
        if not self.enabled:
            return

        self._ship_ref = ship
        self._sim_time = getattr(ship, 'sim_time', self._sim_time + dt)

        # Get weapons damage factor
        if hasattr(ship, 'damage_model'):
            self._damage_factor = ship.damage_model.get_combined_factor("weapons")
        else:
            self._damage_factor = 1.0

        # Update all truth weapons
        for weapon in self.truth_weapons.values():
            weapon.tick(dt, self._sim_time)

        # Update firing solutions from targeting system
        self._update_weapon_solutions(ship)

    def _update_weapon_solutions(self, ship):
        """Update firing solutions for all weapons."""
        targeting = ship.systems.get("targeting")
        if not targeting:
            return

        # Check if we have a locked target with data
        if not targeting.locked_target or not targeting.target_data:
            return

        # Calculate solutions for each truth weapon
        target_data = targeting.target_data
        for weapon_id, weapon in self.truth_weapons.items():
            weapon.calculate_solution(
                shooter_pos=ship.position,
                shooter_vel=ship.velocity,
                target_pos=target_data.get("position", {}),
                target_vel=target_data.get("velocity", {"x": 0, "y": 0, "z": 0}),
                target_id=targeting.locked_target,
                sim_time=self._sim_time,
            )

    def fire_weapon(self, weapon_id: str, target_ship=None) -> dict:
        """Fire a specific weapon.

        Args:
            weapon_id: Weapon mount identifier
            target_ship: Target ship object (optional, uses locked target)

        Returns:
            dict: Fire result
        """
        if not self._ship_ref:
            return error_dict("NO_SHIP", "Ship reference not available")

        weapon = self.truth_weapons.get(weapon_id)
        if not weapon:
            return error_dict("UNKNOWN_WEAPON", f"Weapon '{weapon_id}' not found")

        if self._damage_factor <= 0.0:
            return error_dict("WEAPONS_DESTROYED", "Weapons system has failed")

        # Get power manager
        power = self._ship_ref.systems.get("power") or self._ship_ref.systems.get("power_management")

        # Get target from targeting system if not provided
        if target_ship is None:
            targeting = self._ship_ref.systems.get("targeting")
            if targeting and targeting.locked_target:
                # Need to resolve target from simulator
                # This will be passed in via params
                pass

        # Fire!
        result = weapon.fire(
            sim_time=self._sim_time,
            power_manager=power,
            target_ship=target_ship,
            ship_id=self._ship_ref.id,
            damage_factor=self._damage_factor,
            damage_model=self._ship_ref.damage_model if hasattr(self._ship_ref, "damage_model") else None,
            event_bus=self._ship_ref.event_bus if hasattr(self._ship_ref, "event_bus") else None,
        )

        if result.get("ok"):
            self.shots_fired += 1
            if result.get("hit"):
                self.hits += 1
                self.damage_dealt += result.get("damage", 0)
            self.engaging = True

        return result

    def fire_all_ready(self, target_ship=None) -> dict:
        """Fire all weapons that have ready solutions.

        Args:
            target_ship: Target ship object

        Returns:
            dict: Combined fire results
        """
        results = []
        for weapon_id, weapon in self.truth_weapons.items():
            if weapon.can_fire(self._sim_time):
                solution = weapon.current_solution
                if solution and solution.ready_to_fire:
                    result = self.fire_weapon(weapon_id, target_ship)
                    results.append({
                        "weapon_id": weapon_id,
                        **result
                    })

        return {
            "ok": True,
            "weapons_fired": len(results),
            "results": results
        }

    def get_ready_weapons(self) -> List[str]:
        """Get list of weapons ready to fire.

        Returns:
            list: Weapon IDs that are ready
        """
        ready = []
        for weapon_id, weapon in self.truth_weapons.items():
            if weapon.can_fire(self._sim_time):
                solution = weapon.current_solution
                if solution and solution.ready_to_fire:
                    ready.append(weapon_id)
        return ready

    def get_weapon_status(self, weapon_id: str) -> dict:
        """Get status of a specific weapon.

        Args:
            weapon_id: Weapon mount identifier

        Returns:
            dict: Weapon status
        """
        weapon = self.truth_weapons.get(weapon_id)
        if not weapon:
            return error_dict("UNKNOWN_WEAPON", f"Weapon '{weapon_id}' not found")

        return {
            "ok": True,
            **weapon.get_state()
        }

    def resupply(self) -> dict:
        """Resupply all weapons with ammunition.

        Returns:
            dict: Resupply results
        """
        results = []
        for weapon_id, weapon in self.truth_weapons.items():
            if weapon.specs.ammo_capacity:
                prev_ammo = weapon.ammo
                weapon.ammo = weapon.specs.ammo_capacity
                results.append({
                    "weapon_id": weapon_id,
                    "previous": prev_ammo,
                    "current": weapon.ammo,
                    "resupplied": weapon.specs.ammo_capacity - (prev_ammo or 0)
                })

        return success_dict(
            f"Resupplied {len(results)} weapons",
            weapons=results
        )

    def command(self, action: str, params: dict):
        """Handle combat commands.

        Args:
            action: Command action
            params: Parameters

        Returns:
            dict: Result
        """
        if action == "fire":
            weapon_id = params.get("weapon_id") or params.get("weapon")
            if not weapon_id:
                return error_dict("MISSING_PARAMETER", "weapon_id required")

            # Get target ship from params
            target_ship = None
            target_id = params.get("target") or params.get("target_id")
            if target_id:
                all_ships = params.get("all_ships", {})
                target_ship = all_ships.get(target_id)

            return self.fire_weapon(weapon_id, target_ship)

        elif action == "fire_all":
            target_ship = None
            target_id = params.get("target") or params.get("target_id")
            if target_id:
                all_ships = params.get("all_ships", {})
                target_ship = all_ships.get(target_id)

            return self.fire_all_ready(target_ship)

        elif action == "ready_weapons":
            return success_dict(
                "Ready weapons",
                weapons=self.get_ready_weapons()
            )

        elif action == "weapon_status":
            weapon_id = params.get("weapon_id") or params.get("weapon")
            if weapon_id:
                return self.get_weapon_status(weapon_id)
            return self.get_state()

        elif action == "resupply":
            return self.resupply()

        elif action == "status":
            return self.get_state()

        return super().command(action, params)

    def get_state(self) -> dict:
        """Get combat system state.

        Returns:
            dict: State
        """
        state = super().get_state()

        weapons_state = {}
        for weapon_id, weapon in self.truth_weapons.items():
            weapons_state[weapon_id] = weapon.get_state()

        state.update({
            "damage_factor": self._damage_factor,
            "engaging": self.engaging,
            "shots_fired": self.shots_fired,
            "hits": self.hits,
            "accuracy": self.hits / self.shots_fired if self.shots_fired > 0 else 0.0,
            "damage_dealt": self.damage_dealt,
            "truth_weapons": weapons_state,
            "ready_weapons": self.get_ready_weapons(),
        })
        return state
