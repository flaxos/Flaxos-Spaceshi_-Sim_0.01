# hybrid/systems/combat/combat_system.py
"""Combat system for coordinating weapons, targeting, and damage.

Sprint C: Combat loop v1 implementation.
Integrates truth weapons with targeting pipeline.
Torpedo tubes provide guided, self-propelled munitions.
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
from hybrid.systems.combat.torpedo_manager import (
    TORPEDO_MASS, TORPEDO_FUEL_MASS,
)

logger = logging.getLogger(__name__)


class CombatSystem(BaseSystem):
    """Combat system managing weapons and engagement.

    Provides:
    - Truth weapon management (railgun, PDC)
    - Torpedo tubes (guided self-propelled munitions)
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
                - torpedoes: Number of torpedo tubes (default 0)
                - torpedo_capacity: Torpedoes per tube (default 4)
                - weapons: List of custom weapon configs
        """
        super().__init__(config)

        # Initialize truth weapons
        self.truth_weapons: Dict[str, TruthWeapon] = {}

        # Build firing arc lookup from weapon_mounts config
        arc_lookup: Dict[str, dict] = {}
        for mount in config.get("weapon_mounts", []):
            mid = mount.get("mount_id", "")
            if "firing_arc" in mount:
                arc_lookup[mid] = mount["firing_arc"]

        # Create railguns
        num_railguns = config.get("railguns", config.get("railgun_mounts", 1))
        for i in range(num_railguns):
            mount_id = f"railgun_{i+1}"
            weapon = create_railgun(mount_id)
            weapon.firing_arc = arc_lookup.get(mount_id)
            self.truth_weapons[mount_id] = weapon

        # Create PDCs
        num_pdcs = config.get("pdcs", config.get("pdc_turrets", 2))
        for i in range(num_pdcs):
            mount_id = f"pdc_{i+1}"
            weapon = create_pdc(mount_id)
            weapon.firing_arc = arc_lookup.get(mount_id)
            self.truth_weapons[mount_id] = weapon

        # Torpedo tubes
        self.torpedo_tubes = config.get("torpedoes", config.get("torpedo_tubes", 0))
        self.torpedo_capacity = config.get("torpedo_capacity", 4)  # Per tube
        self.torpedoes_loaded: int = self.torpedo_tubes * self.torpedo_capacity
        self.torpedo_reload_time = config.get("torpedo_reload_time", 15.0)  # seconds
        self._torpedo_cooldown = 0.0  # Time until next launch
        self.torpedoes_launched = 0

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

        # Projectile manager reference (set by simulator each tick)
        self._projectile_manager = None

        # Torpedo manager reference (set by simulator each tick)
        self._torpedo_manager = None

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

        # Get weapons damage factor (includes cascade effects)
        if hasattr(ship, 'get_effective_factor'):
            self._damage_factor = ship.get_effective_factor("weapons")
        elif hasattr(ship, 'damage_model'):
            self._damage_factor = ship.damage_model.get_combined_factor("weapons")
        else:
            self._damage_factor = 1.0

        # Update all truth weapons
        for weapon in self.truth_weapons.values():
            weapon.tick(dt, self._sim_time)

        # Update torpedo tube cooldown
        if self._torpedo_cooldown > 0:
            self._torpedo_cooldown = max(0, self._torpedo_cooldown - dt)

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
        track_quality = getattr(targeting, 'track_quality', 1.0)

        # Get target acceleration for confidence calculation
        target_accel = None
        if hasattr(targeting, '_get_target_accel'):
            target_accel = targeting._get_target_accel()

        for weapon_id, weapon in self.truth_weapons.items():
            weapon.calculate_solution(
                shooter_pos=ship.position,
                shooter_vel=ship.velocity,
                target_pos=target_data.get("position", {}),
                target_vel=target_data.get("velocity", {"x": 0, "y": 0, "z": 0}),
                target_id=targeting.locked_target,
                sim_time=self._sim_time,
                track_quality=track_quality,
                shooter_angular_vel=getattr(ship, 'angular_velocity', None),
                weapon_damage_factor=self._damage_factor,
                target_accel=target_accel,
            )

    def fire_weapon(self, weapon_id: str, target_ship=None, target_subsystem: str = None) -> dict:
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

        # Cold-drift mode disables all weapons (reactor offline)
        if getattr(self._ship_ref, "_cold_drift_active", False):
            return error_dict("COLD_DRIFT", "Weapons offline — ship is in cold-drift mode")

        # Get power manager
        power = self._ship_ref.systems.get("power") or self._ship_ref.systems.get("power_management")

        # Get target from targeting system if not provided
        if target_ship is None:
            targeting = self._ship_ref.systems.get("targeting")
            if targeting and targeting.locked_target:
                # Need to resolve target from simulator
                # This will be passed in via params
                pass

        if target_subsystem is None:
            targeting = self._ship_ref.systems.get("targeting")
            if targeting and hasattr(targeting, "target_subsystem"):
                target_subsystem = targeting.target_subsystem

        # Fire! Pass projectile_manager for ballistic weapons (railgun)
        result = weapon.fire(
            sim_time=self._sim_time,
            power_manager=power,
            target_ship=target_ship,
            ship_id=self._ship_ref.id,
            damage_factor=self._damage_factor,
            damage_model=self._ship_ref.damage_model if hasattr(self._ship_ref, "damage_model") else None,
            event_bus=self._ship_ref.event_bus if hasattr(self._ship_ref, "event_bus") else None,
            target_subsystem=target_subsystem,
            projectile_manager=self._projectile_manager,
            shooter_pos=self._ship_ref.position if hasattr(self._ship_ref, "position") else None,
            shooter_vel=self._ship_ref.velocity if hasattr(self._ship_ref, "velocity") else None,
        )

        if result.get("ok"):
            rounds = result.get("rounds_fired", 1)
            self.shots_fired += rounds
            hits = result.get("hits", 1 if result.get("hit") else 0)
            self.hits += hits
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

    def launch_torpedo(self, target_id: str, profile: str = "direct", all_ships: dict = None) -> dict:
        """Launch a torpedo at a target.

        Args:
            target_id: Target ship ID
            profile: Attack profile ("direct" or "evasive")
            all_ships: Dict of all ships for target resolution

        Returns:
            dict: Launch result
        """
        if not self._ship_ref:
            return error_dict("NO_SHIP", "Ship reference not available")

        if self.torpedo_tubes <= 0:
            return error_dict("NO_TUBES", "Ship has no torpedo tubes")

        if self.torpedoes_loaded <= 0:
            return error_dict("NO_TORPEDOES", "No torpedoes remaining")

        if self._torpedo_cooldown > 0:
            return error_dict("TORPEDO_CYCLING",
                              f"Torpedo tube cycling ({self._torpedo_cooldown:.1f}s remaining)")

        if self._damage_factor <= 0.0:
            return error_dict("WEAPONS_DESTROYED", "Weapons system has failed")

        if getattr(self._ship_ref, "_cold_drift_active", False):
            return error_dict("COLD_DRIFT", "Weapons offline — ship is in cold-drift mode")

        if not self._torpedo_manager:
            return error_dict("NO_TORPEDO_MANAGER", "Torpedo manager not available")

        # Resolve target
        all_ships = all_ships or {}
        target_ship = all_ships.get(target_id)

        # Get target position/velocity from targeting system or direct reference
        target_pos = None
        target_vel = None
        if target_ship:
            target_pos = target_ship.position
            target_vel = target_ship.velocity
        else:
            targeting = self._ship_ref.systems.get("targeting")
            if targeting and hasattr(targeting, "target_data") and targeting.target_data:
                target_pos = targeting.target_data.get("position")
                target_vel = targeting.target_data.get("velocity", {"x": 0, "y": 0, "z": 0})

        if not target_pos:
            return error_dict("NO_TARGET_DATA", "No position data for target")

        # Consume torpedo
        self.torpedoes_loaded -= 1
        self._torpedo_cooldown = self.torpedo_reload_time
        self.torpedoes_launched += 1

        # Spawn torpedo — inherits launcher velocity
        torpedo = self._torpedo_manager.spawn(
            shooter_id=self._ship_ref.id,
            target_id=target_id,
            position=dict(self._ship_ref.position),
            velocity=dict(self._ship_ref.velocity),
            sim_time=self._sim_time,
            target_pos=dict(target_pos),
            target_vel=dict(target_vel) if target_vel else {"x": 0, "y": 0, "z": 0},
            profile=profile,
        )

        # Generate heat from torpedo launch (exhaust backblast)
        if hasattr(self._ship_ref, "damage_model"):
            self._ship_ref.damage_model.add_heat(
                "weapons", 30.0,
                self._ship_ref.event_bus if hasattr(self._ship_ref, "event_bus") else None,
                self._ship_ref.id,
            )

        return success_dict(
            f"Torpedo launched at {target_id}",
            torpedo_id=torpedo.id,
            target=target_id,
            profile=profile,
            torpedoes_remaining=self.torpedoes_loaded,
            reload_time=self.torpedo_reload_time,
        )

    def get_torpedo_status(self) -> dict:
        """Get torpedo system status.

        Returns:
            dict: Torpedo status
        """
        return success_dict(
            "Torpedo status",
            tubes=self.torpedo_tubes,
            loaded=self.torpedoes_loaded,
            capacity=self.torpedo_tubes * self.torpedo_capacity,
            cooldown=round(self._torpedo_cooldown, 1),
            launched=self.torpedoes_launched,
        )

    def get_total_ammo_mass(self) -> float:
        """Get total mass of all ammunition across all weapons.

        Used by ship._update_mass() for dynamic mass calculation (F=ma).
        Expending ammo makes the ship lighter and more maneuverable.
        Includes torpedo mass.

        Returns:
            float: Total ammunition mass in kg.
        """
        total = 0.0
        for weapon in self.truth_weapons.values():
            total += weapon.get_ammo_mass()
        # Torpedoes are heavy ordnance
        total += self.torpedoes_loaded * TORPEDO_MASS
        return total

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

            target_subsystem = params.get("target_subsystem")
            return self.fire_weapon(weapon_id, target_ship, target_subsystem)

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

        elif action == "set_pdc_mode":
            mode = params.get("mode")
            if mode not in ("auto", "manual", "hold_fire"):
                return error_dict("INVALID_MODE", "PDC mode must be 'auto', 'manual', or 'hold_fire'")
            affected = []
            for mount_id, weapon in self.truth_weapons.items():
                if mount_id.startswith("pdc"):
                    weapon.pdc_mode = mode
                    weapon.enabled = mode != "hold_fire"
                    affected.append(mount_id)
            if not affected:
                return error_dict("NO_PDC", "No PDC mounts available")
            return success_dict(f"PDC mode set to {mode.upper()}", mode=mode, affected_mounts=affected)

        elif action == "launch_torpedo":
            target_id = params.get("target")
            if not target_id and self._ship_ref:
                targeting = self._ship_ref.systems.get("targeting")
                if targeting and targeting.locked_target:
                    target_id = targeting.locked_target
            if not target_id:
                return error_dict("NO_TARGET", "No target designated for torpedo launch")
            profile = params.get("profile", "direct")
            all_ships = params.get("all_ships", {})
            return self.launch_torpedo(target_id, profile, all_ships)

        elif action == "torpedo_status":
            return self.get_torpedo_status()

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

        # Summarize PDC mode from PDC mounts
        pdc_mode = "hold_fire"
        for w in self.truth_weapons.values():
            if w.mount_id.startswith("pdc"):
                pdc_mode = getattr(w, "pdc_mode", "auto")
                break

        state.update({
            "damage_factor": self._damage_factor,
            "engaging": self.engaging,
            "shots_fired": self.shots_fired,
            "hits": self.hits,
            "accuracy": self.hits / self.shots_fired if self.shots_fired > 0 else 0.0,
            "damage_dealt": self.damage_dealt,
            "total_ammo_mass": self.get_total_ammo_mass(),
            "truth_weapons": weapons_state,
            "ready_weapons": self.get_ready_weapons(),
            "pdc_mode": pdc_mode,
            "torpedoes": {
                "tubes": self.torpedo_tubes,
                "loaded": self.torpedoes_loaded,
                "capacity": self.torpedo_tubes * self.torpedo_capacity,
                "cooldown": round(self._torpedo_cooldown, 1),
                "launched": self.torpedoes_launched,
                "mass_per_torpedo": TORPEDO_MASS,
            },
        })
        return state
