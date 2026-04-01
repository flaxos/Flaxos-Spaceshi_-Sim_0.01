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
    RAILGUN_SPECS, PDC_SPECS, WeaponSpecs, SlugType,
)
from hybrid.systems.combat.torpedo_manager import (
    TORPEDO_MASS, TORPEDO_FUEL_MASS,
    MISSILE_MASS, MISSILE_FUEL_MASS,
    MunitionType, MISSILE_FLIGHT_PROFILES,
    WarheadType, GuidanceMode,
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
                - missiles: Number of missile launchers (default 0)
                - missile_capacity: Missiles per launcher (default 8)
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

        # Torpedo tubes — heavy guided munitions for slow/large targets
        self.torpedo_tubes = config.get("torpedoes", config.get("torpedo_tubes", 0))
        self.torpedo_capacity = config.get("torpedo_capacity", 4)  # Per tube
        self.torpedoes_loaded: int = self.torpedo_tubes * self.torpedo_capacity
        self.torpedo_reload_time = config.get("torpedo_reload_time", 15.0)  # seconds
        self._torpedo_cooldown = 0.0  # Time until next launch
        self.torpedoes_launched = 0

        # Missile launchers — share hardpoints with torpedoes, but tracked
        # separately because they are different ordnance loaded into the
        # same launcher bays.  missile_capacity is total missiles carried,
        # not per-tube (since they share torpedo tubes for launch).
        self.missile_launchers = config.get("missiles", config.get("missile_launchers", 0))
        self.missile_capacity = config.get("missile_capacity", 8)
        self.missiles_loaded: int = self.missile_launchers * self.missile_capacity
        self.missile_reload_time = config.get("missile_reload_time", 8.0)  # seconds — faster than torpedoes
        self._missile_cooldown = 0.0
        self.missiles_launched = 0

        # PDC defense state -----------------------------------------------
        # Priority defense: human-ordered engagement list of torpedo IDs
        self.pdc_priority_targets: List[str] = []
        # Network defense: per-PDC current engagement {mount_id: torpedo_id}
        self._pdc_engagements: Dict[str, Optional[str]] = {}
        # Re-acquisition delay after a PDC destroys a target (seconds).
        # Models the realistic tracker slew time to acquire the next threat.
        self._pdc_reacquire_delay: float = 0.2
        # Per-PDC cooldown remaining after destroying a target
        self._pdc_reacquire_timers: Dict[str, float] = {}
        # Per-PDC intercept statistics for weapons status panel
        self.pdc_stats: Dict[str, Dict[str, int]] = {}

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

        # Initialise per-PDC stats after weapons are created
        for mount_id in self.truth_weapons:
            if mount_id.startswith("pdc"):
                self.pdc_stats[mount_id] = {
                    "intercepts": 0,
                    "misses": 0,
                    "engagements": 0,
                }

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

        # Update launcher cooldowns (torpedo and missile share the tick)
        if self._torpedo_cooldown > 0:
            self._torpedo_cooldown = max(0, self._torpedo_cooldown - dt)
        if self._missile_cooldown > 0:
            self._missile_cooldown = max(0, self._missile_cooldown - dt)

        # Tick down PDC re-acquisition timers (post-kill slew delay)
        expired = []
        for mid, remaining in self._pdc_reacquire_timers.items():
            remaining -= dt
            if remaining <= 0:
                expired.append(mid)
            else:
                self._pdc_reacquire_timers[mid] = remaining
        for mid in expired:
            del self._pdc_reacquire_timers[mid]

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
                # Ship orientation needed for firing arc checks — arcs are
                # defined relative to the ship's nose, not world space.
                shooter_heading=getattr(ship, 'orientation', None),
            )

    def fire_weapon(
        self, weapon_id: str, target_ship=None,
        target_subsystem: str = None, slug_type: Optional[str] = None,
    ) -> dict:
        """Fire a specific weapon.

        Args:
            weapon_id: Weapon mount identifier
            target_ship: Target ship object (optional, uses locked target)
            target_subsystem: Specific subsystem to target
            slug_type: Railgun slug variant (standard/sabot/fragmentation).
                Ignored for non-railgun weapons.

        Returns:
            dict: Fire result
        """
        if not self._ship_ref:
            return error_dict("NO_SHIP", "Ship reference not available")

        weapon = self.truth_weapons.get(weapon_id)
        if not weapon:
            return error_dict("UNKNOWN_WEAPON", f"Weapon '{weapon_id}' not found")

        if self._damage_factor <= 0.0:
            # Distinguish overheated (temporary) from destroyed (permanent)
            if hasattr(self._ship_ref, 'damage_model'):
                weapons_sub = self._ship_ref.damage_model.subsystems.get("weapons")
                if weapons_sub and weapons_sub.is_overheated():
                    return error_dict("WEAPONS_OVERHEATED", "Weapons offline — overheating, wait for cooldown")
            return error_dict("WEAPONS_DESTROYED", "Weapons system has failed")

        # Cold-drift mode disables all weapons (reactor offline)
        if getattr(self._ship_ref, "_cold_drift_active", False):
            return error_dict("COLD_DRIFT", "Weapons offline — ship is in cold-drift mode")

        # Get power manager
        power = self._ship_ref.systems.get("power_management") or self._ship_ref.systems.get("power")

        # Get target from targeting system if not provided
        if target_ship is None:
            targeting = self._ship_ref.systems.get("targeting")
            if targeting and targeting.locked_target:
                locked_id = targeting.locked_target
                # Resolve contact ID to real ship ID via sensor contact tracker
                all_ships = getattr(self._ship_ref, "_all_ships_ref", None) or []
                ships_dict = {s.id: s for s in all_ships} if isinstance(all_ships, list) else {}
                target_ship = ships_dict.get(locked_id)
                if not target_ship:
                    sensors = self._ship_ref.systems.get("sensors")
                    if sensors and hasattr(sensors, "contact_tracker"):
                        for real_id, stable_id in sensors.contact_tracker.id_mapping.items():
                            if stable_id == locked_id:
                                target_ship = ships_dict.get(real_id)
                                break

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
            slug_type=slug_type,
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

    def launch_torpedo(
        self, target_id: str, profile: str = "direct", all_ships: dict = None,
        warhead_type: Optional[str] = None, guidance_mode: Optional[str] = None,
    ) -> dict:
        """Launch a torpedo at a target.

        Args:
            target_id: Target ship ID
            profile: Attack profile ("direct" or "evasive")
            all_ships: Dict of all ships for target resolution
            warhead_type: Warhead variant (fragmentation/shaped_charge/emp).
                Defaults to fragmentation.
            guidance_mode: Guidance CPU level (dumb/guided/smart).
                Defaults to guided.

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
            # Distinguish overheated (temporary) from destroyed (permanent)
            if hasattr(self._ship_ref, 'damage_model'):
                weapons_sub = self._ship_ref.damage_model.subsystems.get("weapons")
                if weapons_sub and weapons_sub.is_overheated():
                    return error_dict("WEAPONS_OVERHEATED", "Weapons offline — overheating, wait for cooldown")
            return error_dict("WEAPONS_DESTROYED", "Weapons system has failed")

        if getattr(self._ship_ref, "_cold_drift_active", False):
            return error_dict("COLD_DRIFT", "Weapons offline — ship is in cold-drift mode")

        if not self._torpedo_manager:
            return error_dict("NO_TORPEDO_MANAGER", "Torpedo manager not available")

        # Resolve target — contact IDs (e.g. "C001") must be mapped back to
        # real ship IDs (e.g. "pirate01") so the torpedo manager can look up
        # the target in the ships dict for guidance and proximity detonation.
        all_ships = all_ships or {}
        resolved_target_id = target_id
        target_ship = all_ships.get(target_id)

        if not target_ship:
            # target_id may be a stable contact ID from the sensor system.
            # Reverse-lookup: find the real ship ID from the contact tracker.
            sensors = self._ship_ref.systems.get("sensors")
            if sensors and hasattr(sensors, "contact_tracker"):
                tracker = sensors.contact_tracker
                for real_id, stable_id in tracker.id_mapping.items():
                    if stable_id == target_id:
                        resolved_target_id = real_id
                        target_ship = all_ships.get(real_id)
                        break

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

        # Spawn torpedo — inherits launcher velocity.
        # Use resolved_target_id (real ship ID) so the torpedo manager can
        # look up the target ship for guidance updates and proximity fuse.
        torpedo = self._torpedo_manager.spawn(
            shooter_id=self._ship_ref.id,
            target_id=resolved_target_id,
            position=dict(self._ship_ref.position),
            velocity=dict(self._ship_ref.velocity),
            sim_time=self._sim_time,
            target_pos=dict(target_pos),
            target_vel=dict(target_vel) if target_vel else {"x": 0, "y": 0, "z": 0},
            profile=profile,
            warhead_type=warhead_type,
            guidance_mode=guidance_mode,
        )

        # Generate heat from torpedo launch (exhaust backblast).
        # 15 heat per launch — a full 12-torpedo salvo with pauses is
        # sustainable. Players can fire 6 torpedoes before needing to
        # wait for dissipation (weapons max_heat 120, threshold 85% = 102).
        if hasattr(self._ship_ref, "damage_model"):
            self._ship_ref.damage_model.add_heat(
                "weapons", 15.0,
                self._ship_ref.event_bus if hasattr(self._ship_ref, "event_bus") else None,
                self._ship_ref.id,
            )

        return success_dict(
            f"Torpedo launched at {resolved_target_id}",
            torpedo_id=torpedo.id,
            target=target_id,
            profile=profile,
            warhead_type=torpedo.warhead_type,
            guidance_mode=torpedo.guidance_mode,
            torpedoes_remaining=self.torpedoes_loaded,
            reload_time=self.torpedo_reload_time,
        )

    def launch_missile(
        self, target_id: str, profile: str = "direct", all_ships: dict = None,
        warhead_type: Optional[str] = None, guidance_mode: Optional[str] = None,
    ) -> dict:
        """Launch a missile at a target.

        Missiles are lighter, faster, higher-G munitions designed for
        maneuvering ships.  They share the torpedo manager for flight
        simulation but draw from a separate magazine.

        Args:
            target_id: Target ship ID
            profile: Flight profile ("direct", "evasive", "terminal_pop", "bracket")
            all_ships: Dict of all ships for target resolution
            warhead_type: Warhead variant (fragmentation/shaped_charge/emp).
                Defaults to fragmentation.
            guidance_mode: Guidance CPU level (dumb/guided/smart).
                Defaults to guided.

        Returns:
            dict: Launch result
        """
        if not self._ship_ref:
            return error_dict("NO_SHIP", "Ship reference not available")

        if self.missile_launchers <= 0:
            return error_dict("NO_LAUNCHERS", "Ship has no missile launchers")

        if self.missiles_loaded <= 0:
            return error_dict("NO_MISSILES", "No missiles remaining")

        if self._missile_cooldown > 0:
            return error_dict("MISSILE_CYCLING",
                              f"Missile launcher cycling ({self._missile_cooldown:.1f}s remaining)")

        if profile not in MISSILE_FLIGHT_PROFILES:
            return error_dict("INVALID_PROFILE",
                              f"Unknown flight profile '{profile}'. "
                              f"Valid: {', '.join(sorted(MISSILE_FLIGHT_PROFILES))}")

        if self._damage_factor <= 0.0:
            if hasattr(self._ship_ref, 'damage_model'):
                weapons_sub = self._ship_ref.damage_model.subsystems.get("weapons")
                if weapons_sub and weapons_sub.is_overheated():
                    return error_dict("WEAPONS_OVERHEATED",
                                      "Weapons offline — overheating, wait for cooldown")
            return error_dict("WEAPONS_DESTROYED", "Weapons system has failed")

        if getattr(self._ship_ref, "_cold_drift_active", False):
            return error_dict("COLD_DRIFT", "Weapons offline — ship is in cold-drift mode")

        if not self._torpedo_manager:
            return error_dict("NO_TORPEDO_MANAGER", "Torpedo manager not available")

        # Resolve target — same contact-ID lookup as launch_torpedo
        all_ships = all_ships or {}
        resolved_target_id = target_id
        target_ship = all_ships.get(target_id)

        if not target_ship:
            sensors = self._ship_ref.systems.get("sensors")
            if sensors and hasattr(sensors, "contact_tracker"):
                tracker = sensors.contact_tracker
                for real_id, stable_id in tracker.id_mapping.items():
                    if stable_id == target_id:
                        resolved_target_id = real_id
                        target_ship = all_ships.get(real_id)
                        break

        # Get target position/velocity
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

        # Consume missile
        self.missiles_loaded -= 1
        self._missile_cooldown = self.missile_reload_time
        self.missiles_launched += 1

        # Spawn missile through the torpedo manager with MISSILE type
        missile = self._torpedo_manager.spawn(
            shooter_id=self._ship_ref.id,
            target_id=resolved_target_id,
            position=dict(self._ship_ref.position),
            velocity=dict(self._ship_ref.velocity),
            sim_time=self._sim_time,
            target_pos=dict(target_pos),
            target_vel=dict(target_vel) if target_vel else {"x": 0, "y": 0, "z": 0},
            profile=profile,
            munition_type=MunitionType.MISSILE,
            warhead_type=warhead_type,
            guidance_mode=guidance_mode,
        )

        # Less heat than torpedo (smaller motor exhaust).
        # 8 heat per launch — missiles are lighter ordnance with smaller
        # backblast. A full 8-missile salvo (64 heat) stays well under
        # the 102 overheat threshold even without cooling pauses.
        if hasattr(self._ship_ref, "damage_model"):
            self._ship_ref.damage_model.add_heat(
                "weapons", 8.0,
                self._ship_ref.event_bus if hasattr(self._ship_ref, "event_bus") else None,
                self._ship_ref.id,
            )

        return success_dict(
            f"Missile launched at {resolved_target_id}",
            missile_id=missile.id,
            target=target_id,
            profile=profile,
            warhead_type=missile.warhead_type,
            guidance_mode=missile.guidance_mode,
            missiles_remaining=self.missiles_loaded,
            reload_time=self.missile_reload_time,
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

    def get_missile_status(self) -> dict:
        """Get missile system status.

        Returns:
            dict: Missile status
        """
        return success_dict(
            "Missile status",
            launchers=self.missile_launchers,
            loaded=self.missiles_loaded,
            capacity=self.missile_launchers * self.missile_capacity,
            cooldown=round(self._missile_cooldown, 1),
            launched=self.missiles_launched,
        )

    def get_total_ammo_mass(self) -> float:
        """Get total mass of all ammunition across all weapons.

        Used by ship._update_mass() for dynamic mass calculation (F=ma).
        Expending ammo makes the ship lighter and more maneuverable.
        Includes torpedo and missile mass.

        Returns:
            float: Total ammunition mass in kg.
        """
        total = 0.0
        for weapon in self.truth_weapons.values():
            total += weapon.get_ammo_mass()
        # Torpedoes are heavy ordnance
        total += self.torpedoes_loaded * TORPEDO_MASS
        # Missiles are lighter but still have mass
        total += self.missiles_loaded * MISSILE_MASS
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
            # GUI sends mount_id, accept all common param names
            weapon_id = (params.get("weapon_id")
                         or params.get("weapon")
                         or params.get("mount_id"))
            if not weapon_id:
                return error_dict("MISSING_PARAMETER", "weapon_id required")

            # Resolve target — contact IDs (e.g. "C001") must be mapped
            # back to real ship IDs so we can look up the target in all_ships.
            target_ship = None
            target_id = params.get("target") or params.get("target_id")
            if target_id:
                # Build ships dict from _all_ships_ref (params never includes all_ships)
                all_ships_list = getattr(self._ship_ref, "_all_ships_ref", None) or []
                all_ships = {s.id: s for s in all_ships_list} if isinstance(all_ships_list, list) else {}
                target_ship = all_ships.get(target_id)

                if not target_ship:
                    sensors = self._ship_ref.systems.get("sensors")
                    if sensors and hasattr(sensors, "contact_tracker"):
                        tracker = sensors.contact_tracker
                        for real_id, stable_id in tracker.id_mapping.items():
                            if stable_id == target_id:
                                target_ship = all_ships.get(real_id)
                                break

            target_subsystem = params.get("target_subsystem")
            slug_type = params.get("slug_type")
            return self.fire_weapon(weapon_id, target_ship, target_subsystem, slug_type=slug_type)

        elif action == "fire_all":
            target_ship = None
            target_id = params.get("target") or params.get("target_id")
            if target_id:
                all_ships_list = getattr(self._ship_ref, "_all_ships_ref", None) or []
                all_ships = {s.id: s for s in all_ships_list} if isinstance(all_ships_list, list) else {}
                target_ship = all_ships.get(target_id)

                if not target_ship:
                    sensors = self._ship_ref.systems.get("sensors")
                    if sensors and hasattr(sensors, "contact_tracker"):
                        tracker = sensors.contact_tracker
                        for real_id, stable_id in tracker.id_mapping.items():
                            if stable_id == target_id:
                                target_ship = all_ships.get(real_id)
                                break

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
            valid_modes = ("auto", "manual", "hold_fire", "priority", "network")
            if mode not in valid_modes:
                return error_dict(
                    "INVALID_MODE",
                    f"PDC mode must be one of {valid_modes}, got '{mode}'"
                )
            affected = []
            for mount_id, weapon in self.truth_weapons.items():
                if mount_id.startswith("pdc"):
                    weapon.pdc_mode = mode
                    weapon.enabled = mode != "hold_fire"
                    affected.append(mount_id)
            if not affected:
                return error_dict("NO_PDC", "No PDC mounts available")
            # Clear network engagements when switching modes so stale
            # assignments don't persist across mode changes.
            self._pdc_engagements.clear()
            return success_dict(f"PDC mode set to {mode.upper()}", mode=mode, affected_mounts=affected)

        elif action == "set_pdc_priority":
            torpedo_ids = params.get("torpedo_ids")
            if not isinstance(torpedo_ids, list):
                return error_dict(
                    "INVALID_PARAMETER",
                    "torpedo_ids must be a list of torpedo IDs in priority order"
                )
            self.pdc_priority_targets = list(torpedo_ids)
            return success_dict(
                f"PDC priority queue set ({len(torpedo_ids)} targets)",
                torpedo_ids=self.pdc_priority_targets,
            )

        elif action == "launch_torpedo":
            target_id = params.get("target")
            if not target_id and self._ship_ref:
                targeting = self._ship_ref.systems.get("targeting")
                if targeting and targeting.locked_target:
                    target_id = targeting.locked_target
            if not target_id:
                return error_dict("NO_TARGET", "No target designated for torpedo launch")
            profile = params.get("profile", "direct")
            # Build ships dict from _all_ships_ref (params never includes all_ships)
            all_ships_list = getattr(self._ship_ref, "_all_ships_ref", None) or []
            all_ships = {s.id: s for s in all_ships_list} if isinstance(all_ships_list, list) else {}
            warhead_type = params.get("warhead_type")
            guidance_mode = params.get("guidance_mode")
            return self.launch_torpedo(target_id, profile, all_ships,
                                       warhead_type=warhead_type, guidance_mode=guidance_mode)

        elif action == "launch_missile":
            target_id = params.get("target")
            if not target_id and self._ship_ref:
                targeting = self._ship_ref.systems.get("targeting")
                if targeting and targeting.locked_target:
                    target_id = targeting.locked_target
            if not target_id:
                return error_dict("NO_TARGET", "No target designated for missile launch")
            profile = params.get("profile", "direct")
            # Build ships dict from _all_ships_ref (params never includes all_ships)
            all_ships_list = getattr(self._ship_ref, "_all_ships_ref", None) or []
            all_ships = {s.id: s for s in all_ships_list} if isinstance(all_ships_list, list) else {}
            warhead_type = params.get("warhead_type")
            guidance_mode = params.get("guidance_mode")
            return self.launch_missile(target_id, profile, all_ships,
                                       warhead_type=warhead_type, guidance_mode=guidance_mode)

        elif action == "torpedo_status":
            return self.get_torpedo_status()

        elif action == "missile_status":
            return self.get_missile_status()

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
            "pdc_priority_targets": list(self.pdc_priority_targets),
            "pdc_engagements": dict(self._pdc_engagements),
            "pdc_stats": dict(self.pdc_stats),
            "torpedoes": {
                "tubes": self.torpedo_tubes,
                "loaded": self.torpedoes_loaded,
                "capacity": self.torpedo_tubes * self.torpedo_capacity,
                "cooldown": round(self._torpedo_cooldown, 1),
                "launched": self.torpedoes_launched,
                "mass_per_torpedo": TORPEDO_MASS,
            },
            "missiles": {
                "launchers": self.missile_launchers,
                "loaded": self.missiles_loaded,
                "capacity": self.missile_launchers * self.missile_capacity,
                "cooldown": round(self._missile_cooldown, 1),
                "launched": self.missiles_launched,
                "mass_per_missile": MISSILE_MASS,
            },
        })
        return state
