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
    TruthWeapon, FiringSolution, create_railgun, create_pdc,
    RAILGUN_SPECS, PDC_SPECS, WeaponSpecs, SlugType,
)
from hybrid.systems.combat.torpedo_manager import (
    TORPEDO_MASS, TORPEDO_FUEL_MASS,
    MISSILE_MASS, MISSILE_FUEL_MASS,
    MunitionType, MISSILE_FLIGHT_PROFILES,
    WarheadType, GuidanceMode,
)
from hybrid.systems.combat.auto_fire_manager import AutoFireManager

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

        # Build firing arc and gimbal lookup from weapon_mounts config.
        # Each weapon mount entry may specify:
        #   firing_arc: azimuth/elevation limits for arc-of-fire checks
        #   gimbal: true/false — independent turret tracking
        #   max_rotation_rate: turret slew rate in deg/s (used by gimbal)
        arc_lookup: Dict[str, dict] = {}
        gimbal_lookup: Dict[str, dict] = {}
        for mount in config.get("weapon_mounts", []):
            mid = mount.get("mount_id", "")
            if "firing_arc" in mount:
                arc_lookup[mid] = mount["firing_arc"]
            if mount.get("gimbal"):
                gimbal_lookup[mid] = {
                    "gimbal": True,
                    "max_rotation_rate": mount.get("max_rotation_rate", 30.0),
                }

        # Create railguns
        num_railguns = config.get("railguns", config.get("railgun_mounts", 1))
        for i in range(num_railguns):
            mount_id = f"railgun_{i+1}"
            weapon = create_railgun(mount_id)
            weapon.firing_arc = arc_lookup.get(mount_id)
            self._apply_gimbal_config(weapon, mount_id, gimbal_lookup)
            self.truth_weapons[mount_id] = weapon

        # Create PDCs
        num_pdcs = config.get("pdcs", config.get("pdc_turrets", 2))
        for i in range(num_pdcs):
            mount_id = f"pdc_{i+1}"
            weapon = create_pdc(mount_id)
            weapon.firing_arc = arc_lookup.get(mount_id)
            self._apply_gimbal_config(weapon, mount_id, gimbal_lookup)
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

        # Pre-programmed munition configuration for next launch.
        # Set via program_munition(), consumed on next launch_torpedo/launch_missile.
        self._munition_program: Optional[dict] = None

        # Salvo queue — server-side staggered launch replacing client setTimeout.
        # Each entry: {target, munition_type, profile, warhead_type, guidance_mode, salvo_id}
        self._salvo_queue: list = []
        self._salvo_timer: float = 0.0
        self._salvo_stagger: float = 0.1  # seconds between launches (default 100ms)
        self._next_salvo_id: int = 0

        # Auto-fire manager — server-authoritative fire authorization
        # Replaces the client-side _processAutoExecute() in weapon-controls.js
        self.auto_fire_manager = AutoFireManager()

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

    @staticmethod
    def _apply_gimbal_config(
        weapon: TruthWeapon, mount_id: str, gimbal_lookup: Dict[str, dict],
    ) -> None:
        """Copy gimbal settings from weapon_mounts config to a TruthWeapon.

        Gimbal-enabled weapons slew their turret independently within the
        firing arc, so targets can be tracked without rotating the ship.
        The arc limits from firing_arc are reused as gimbal clamp limits.

        Args:
            weapon: TruthWeapon instance to configure.
            mount_id: Mount identifier for lookup.
            gimbal_lookup: Dict mapping mount_id to gimbal config.
        """
        gcfg = gimbal_lookup.get(mount_id)
        if not gcfg:
            return
        weapon.gimbal_enabled = True
        weapon._gimbal_max_rate = gcfg.get("max_rotation_rate", 30.0)
        # Copy arc limits from the weapon's firing_arc config so the
        # gimbal clamps to the same physical arc as the mount.
        if weapon.firing_arc:
            weapon._gimbal_az_limits = (
                weapon.firing_arc.get("azimuth_min", -180.0),
                weapon.firing_arc.get("azimuth_max", 180.0),
            )
            weapon._gimbal_el_limits = (
                weapon.firing_arc.get("elevation_min", -90.0),
                weapon.firing_arc.get("elevation_max", 90.0),
            )

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

        # Process salvo queue — pop one launch per stagger interval
        self._tick_salvo_queue(dt, ship)

        # Update firing solutions from targeting system
        self._update_weapon_solutions(ship)

        # Auto-fire: check authorized weapons and fire when conditions met.
        # Must run AFTER weapon solutions are updated so the manager sees
        # current ready_to_fire state.
        self.auto_fire_manager.tick(dt, self, ship)

    def _tick_salvo_queue(self, dt: float, ship) -> None:
        """Process the salvo queue, launching one munition per stagger interval.

        The salvo queue decouples the player's "fire salvo" intent from the
        individual launch timing.  Each tick, if enough time has elapsed since
        the last staggered launch, the next queued launch config is popped and
        executed through the normal launch_missile / launch_torpedo path.

        Args:
            dt: Time delta this tick.
            ship: Ship object (needed for all_ships resolution).
        """
        if not self._salvo_queue:
            return

        self._salvo_timer -= dt
        if self._salvo_timer > 0:
            return

        # Pop the next launch from the queue
        launch_cfg = self._salvo_queue.pop(0)
        self._salvo_timer = self._salvo_stagger

        # Build all_ships dict from ship reference
        all_ships_list = getattr(ship, "_all_ships_ref", None) or []
        all_ships = {s.id: s for s in all_ships_list} if isinstance(all_ships_list, list) else {}

        munition_type = launch_cfg.get("munition_type", "missile")
        target = launch_cfg.get("target")
        profile = launch_cfg.get("profile", "direct")
        warhead_type = launch_cfg.get("warhead_type")
        guidance_mode = launch_cfg.get("guidance_mode")

        if munition_type == "torpedo":
            self.launch_torpedo(target, profile, all_ships,
                                warhead_type=warhead_type, guidance_mode=guidance_mode)
        else:
            self.launch_missile(target, profile, all_ships,
                                warhead_type=warhead_type, guidance_mode=guidance_mode)

    def launch_salvo(
        self, target: Optional[str] = None, count: int = 2,
        munition_type: str = "missile", profile: str = "direct",
        stagger_ms: int = 100, warhead_type: Optional[str] = None,
        guidance_mode: Optional[str] = None,
    ) -> dict:
        """Queue a salvo of missiles or torpedoes for staggered server-side launch.

        Replaces the client-side setTimeout stagger with authoritative server
        timing.  If the ship has fewer munitions than requested, a partial
        salvo is queued (fire what you have).

        Args:
            target: Target ship/contact ID (uses locked target if omitted).
            count: Number of munitions to fire (1/2/4/6/8, clamped to ammo).
            munition_type: "missile" or "torpedo".
            profile: Flight profile for missiles, attack profile for torpedoes.
            stagger_ms: Milliseconds between each launch (default 100).
            warhead_type: Optional warhead variant.
            guidance_mode: Optional guidance CPU level.

        Returns:
            dict: {salvo_id, count_queued, munition_type} on success.
        """
        if not self._ship_ref:
            return error_dict("NO_SHIP", "Ship reference not available")

        # Resolve target from targeting system if not provided
        if not target:
            targeting = self._ship_ref.systems.get("targeting")
            if targeting and targeting.locked_target:
                target = targeting.locked_target

        if not target:
            return error_dict("NO_TARGET", "No target designated for salvo launch")

        # Validate munition type and check available ammo
        if munition_type == "torpedo":
            available = self.torpedoes_loaded
            if available <= 0:
                return error_dict("NO_TORPEDOES", "No torpedoes remaining")
        elif munition_type == "missile":
            available = self.missiles_loaded
            if available <= 0:
                return error_dict("NO_MISSILES", "No missiles remaining")
        else:
            return error_dict("INVALID_MUNITION",
                              f"munition_type must be 'missile' or 'torpedo', got '{munition_type}'")

        # Clamp count to available ammo (partial salvo if insufficient)
        count_queued = min(count, available)

        # Assign salvo ID for tracking
        self._next_salvo_id += 1
        salvo_id = f"salvo_{self._next_salvo_id}"

        # Set stagger timing
        self._salvo_stagger = max(stagger_ms / 1000.0, 0.05)  # floor 50ms

        # Queue each launch config
        for _ in range(count_queued):
            self._salvo_queue.append({
                "target": target,
                "munition_type": munition_type,
                "profile": profile,
                "warhead_type": warhead_type,
                "guidance_mode": guidance_mode,
                "salvo_id": salvo_id,
            })

        # Fire the first one immediately (timer starts from zero)
        self._salvo_timer = 0.0

        logger.info(
            "Salvo %s queued: %d x %s at %s (stagger=%dms, profile=%s)",
            salvo_id, count_queued, munition_type, target, stagger_ms, profile,
        )

        return success_dict(
            f"Salvo queued: {count_queued}x {munition_type}",
            salvo_id=salvo_id,
            count_queued=count_queued,
            munition_type=munition_type,
        )

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

    def fire_unguided(self, params: dict) -> dict:
        """Fire a weapon without a targeting lock (MANUAL tier dumb-fire).

        The weapon fires along the ship's nose vector (bore-sight).
        No lead calculation, no confidence check, no lock required.
        Pure point-and-shoot for players who want to aim manually.

        Args:
            params: Dict with:
                weapon_type: "railgun" or "pdc" (required)
                hardpoint_id: str (optional -- specific mount, default: first available)

        Returns:
            dict: Fire result from the weapon, or error.
        """
        if not self._ship_ref:
            return error_dict("NO_SHIP", "Ship reference not available")

        if self._damage_factor <= 0.0:
            if hasattr(self._ship_ref, "damage_model"):
                weapons_sub = self._ship_ref.damage_model.subsystems.get("weapons")
                if weapons_sub and weapons_sub.is_overheated():
                    return error_dict("WEAPONS_OVERHEATED",
                                      "Weapons offline -- overheating, wait for cooldown")
            return error_dict("WEAPONS_DESTROYED", "Weapons system has failed")

        if getattr(self._ship_ref, "_cold_drift_active", False):
            return error_dict("COLD_DRIFT", "Weapons offline -- ship is in cold-drift mode")

        weapon_type = params.get("weapon_type")
        if not weapon_type:
            return error_dict("MISSING_PARAMETER", "weapon_type required ('railgun' or 'pdc')")

        weapon_type = weapon_type.lower()
        if weapon_type not in ("railgun", "pdc"):
            return error_dict("INVALID_PARAMETER",
                              f"weapon_type must be 'railgun' or 'pdc', got '{weapon_type}'")

        hardpoint_id = params.get("hardpoint_id")

        # Find the weapon mount to fire
        weapon: Optional[TruthWeapon] = None
        weapon_id: Optional[str] = None

        if hardpoint_id:
            weapon = self.truth_weapons.get(hardpoint_id)
            if not weapon:
                return error_dict("UNKNOWN_WEAPON", f"Hardpoint '{hardpoint_id}' not found")
            weapon_id = hardpoint_id
        else:
            # Pick the first available mount of the requested type that can fire
            for mid, w in self.truth_weapons.items():
                if mid.startswith(weapon_type) and w.can_fire(self._sim_time):
                    weapon = w
                    weapon_id = mid
                    break
            if weapon is None:
                # Fall back to any mount of the type even if not ready,
                # so we return a meaningful "cycling" / "no_ammo" error
                for mid, w in self.truth_weapons.items():
                    if mid.startswith(weapon_type):
                        weapon = w
                        weapon_id = mid
                        break
            if weapon is None:
                return error_dict("NO_WEAPON",
                                  f"No {weapon_type} mounts available on this ship")

        # Gate: ensure weapon is actually ready to fire before building
        # the bore-sight solution. Unguided fire skips targeting checks
        # but still requires basic weapon readiness (ammo, heat, cycle).
        if not weapon.can_fire(self._sim_time):
            if weapon.ammo is not None and weapon.ammo <= 0:
                reason = "no_ammo"
            elif weapon.reloading:
                reason = "reloading"
            elif weapon.heat >= weapon.max_heat * 0.95:
                reason = "overheated"
            else:
                reason = "not_ready"
            return error_dict("WEAPON_NOT_READY",
                              f"{weapon_type} not ready: {reason}")

        # Build a minimal bore-sight firing solution.
        # Confidence is 0 because there is no computer-assisted tracking.
        # The weapon fires along the ship's current heading (nose vector).
        saved_solution = weapon.current_solution

        bore_sight = FiringSolution(
            valid=True,
            target_id="unguided",
            range_to_target=0.0,
            lead_angle={"pitch": 0.0, "yaw": 0.0},
            intercept_point={"x": 0.0, "y": 0.0, "z": 0.0},
            time_of_flight=0.0,
            confidence=0.0,
            hit_probability=0.0,
            in_range=True,
            in_arc=True,
            tracking=True,
            ready_to_fire=True,
            reason="unguided bore-sight fire",
        )
        weapon.current_solution = bore_sight

        try:
            slug_type = params.get("slug_type")
            result = self.fire_weapon(weapon_id, target_ship=None,
                                       slug_type=slug_type)
        finally:
            # Restore the original solution so the targeting pipeline
            # is not disrupted for subsequent guided engagements.
            weapon.current_solution = saved_solution

        if result.get("ok"):
            result["unguided"] = True

        return result

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

    def program_munition(self, params: dict) -> dict:
        """Pre-configure the next torpedo or missile launch.

        Allows MANUAL-tier players to fine-tune munition parameters before
        firing.  The program is stored and consumed on the next matching
        launch (torpedo or missile).  If the player launches the *other*
        munition type, the program is ignored (not consumed).

        Args:
            params: Dict with keys:
                munition_type (required): "torpedo" or "missile"
                guidance_mode: "dumb", "guided", or "smart"
                warhead_type: "fragmentation", "shaped_charge", or "emp"
                flight_profile: "direct", "evasive", "terminal_pop", "bracket"
                pn_gain: float 1.0-8.0 — override proportional navigation gain
                fuse_distance: float 5-200m — override proximity fuse radius
                terminal_range: float 500-20000m — range for terminal phase
                boost_duration: float 1.0-30.0s — override boost phase length
                datalink: bool — maintain guidance datalink (default true)

        Returns:
            dict: Programmed configuration summary
        """
        munition_type = params.get("munition_type")
        if munition_type not in ("torpedo", "missile"):
            return error_dict(
                "INVALID_MUNITION_TYPE",
                "munition_type must be 'torpedo' or 'missile'"
            )

        program: dict = {"munition_type": munition_type}

        # Validate guidance mode
        guidance_mode = params.get("guidance_mode")
        valid_guidance = {m.value for m in GuidanceMode}
        if guidance_mode is not None:
            if guidance_mode not in valid_guidance:
                return error_dict(
                    "INVALID_GUIDANCE_MODE",
                    f"guidance_mode must be one of {sorted(valid_guidance)}"
                )
            program["guidance_mode"] = guidance_mode

        # Validate warhead type
        warhead_type = params.get("warhead_type")
        valid_warheads = {w.value for w in WarheadType}
        if warhead_type is not None:
            if warhead_type not in valid_warheads:
                return error_dict(
                    "INVALID_WARHEAD_TYPE",
                    f"warhead_type must be one of {sorted(valid_warheads)}"
                )
            program["warhead_type"] = warhead_type

        # Validate flight profile
        flight_profile = params.get("flight_profile")
        if flight_profile is not None:
            valid_profiles = {"direct", "evasive", "terminal_pop", "bracket"}
            if flight_profile not in valid_profiles:
                return error_dict(
                    "INVALID_FLIGHT_PROFILE",
                    f"flight_profile must be one of {sorted(valid_profiles)}"
                )
            program["flight_profile"] = flight_profile

        # Validate pn_gain — clamp to [1.0, 8.0]
        pn_gain = params.get("pn_gain")
        if pn_gain is not None:
            try:
                pn_gain = float(pn_gain)
            except (TypeError, ValueError):
                return error_dict("INVALID_PN_GAIN", "pn_gain must be a number")
            pn_gain = max(1.0, min(8.0, pn_gain))
            program["pn_gain"] = pn_gain

        # Validate fuse_distance — clamp to [5, 200] meters
        fuse_distance = params.get("fuse_distance")
        if fuse_distance is not None:
            try:
                fuse_distance = float(fuse_distance)
            except (TypeError, ValueError):
                return error_dict("INVALID_FUSE_DISTANCE", "fuse_distance must be a number")
            fuse_distance = max(5.0, min(200.0, fuse_distance))
            program["fuse_distance"] = fuse_distance

        # Validate terminal_range — clamp to [500, 20000] meters
        terminal_range = params.get("terminal_range")
        if terminal_range is not None:
            try:
                terminal_range = float(terminal_range)
            except (TypeError, ValueError):
                return error_dict("INVALID_TERMINAL_RANGE", "terminal_range must be a number")
            terminal_range = max(500.0, min(20000.0, terminal_range))
            program["terminal_range"] = terminal_range

        # Validate boost_duration — clamp to [1.0, 30.0] seconds
        boost_duration = params.get("boost_duration")
        if boost_duration is not None:
            try:
                boost_duration = float(boost_duration)
            except (TypeError, ValueError):
                return error_dict("INVALID_BOOST_DURATION", "boost_duration must be a number")
            boost_duration = max(1.0, min(30.0, boost_duration))
            program["boost_duration"] = boost_duration

        # Datalink toggle
        datalink = params.get("datalink")
        if datalink is not None:
            program["datalink"] = bool(datalink)

        self._munition_program = program

        return success_dict(
            f"Munition program set for next {munition_type} launch",
            program=program,
        )

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

        # Apply pre-programmed munition config if it matches this munition type.
        # The program is consumed on launch so only one launch gets the custom
        # parameters.  If the program was set for "missile", it stays for the
        # next missile launch and is not consumed here.
        program = self._munition_program or {}
        if program.get("munition_type") == "torpedo":
            guidance_mode = program.get("guidance_mode", guidance_mode)
            warhead_type = program.get("warhead_type", warhead_type)
            profile = program.get("flight_profile", profile)
            self._munition_program = None  # consumed

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

        # Build custom overrides from the consumed program for torpedo_manager
        custom_overrides = {}
        if program.get("munition_type") == "torpedo":
            for key in ("pn_gain", "fuse_distance", "terminal_range",
                        "boost_duration", "datalink"):
                if key in program:
                    custom_overrides[key] = program[key]

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
            **custom_overrides,
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

        # Apply pre-programmed munition config if it matches missile type.
        program = self._munition_program or {}
        if program.get("munition_type") == "missile":
            guidance_mode = program.get("guidance_mode", guidance_mode)
            warhead_type = program.get("warhead_type", warhead_type)
            profile = program.get("flight_profile", profile)
            self._munition_program = None  # consumed

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

        # Build custom overrides from the consumed program for torpedo_manager
        custom_overrides = {}
        if program.get("munition_type") == "missile":
            for key in ("pn_gain", "fuse_distance", "terminal_range",
                        "boost_duration", "datalink"):
                if key in program:
                    custom_overrides[key] = program[key]

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
            **custom_overrides,
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

        elif action == "fire_unguided":
            return self.fire_unguided(params)

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
            if hasattr(self._ship_ref, "event_bus") and self._ship_ref.event_bus:
                self._ship_ref.event_bus.publish("pdc_mode_changed", {
                    "ship_id": self._ship_ref.id,
                    "mode": mode,
                    "mounts": affected,
                })
            return success_dict(f"PDC mode set to {mode.upper()}", mode=mode, affected_mounts=affected)

        elif action == "set_pdc_priority":
            torpedo_ids = params.get("torpedo_ids")
            if not isinstance(torpedo_ids, list):
                return error_dict(
                    "INVALID_PARAMETER",
                    "torpedo_ids must be a list of torpedo IDs in priority order"
                )
            self.pdc_priority_targets = list(torpedo_ids)
            if hasattr(self._ship_ref, "event_bus") and self._ship_ref.event_bus:
                self._ship_ref.event_bus.publish("pdc_priority_set", {
                    "ship_id": self._ship_ref.id,
                    "torpedo_ids": self.pdc_priority_targets,
                })
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

        elif action == "launch_salvo":
            target_id = params.get("target")
            if not target_id and self._ship_ref:
                targeting = self._ship_ref.systems.get("targeting")
                if targeting and targeting.locked_target:
                    target_id = targeting.locked_target
            count = params.get("count", 2)
            munition_type = params.get("munition_type", "missile")
            profile = params.get("profile", "direct")
            stagger_ms = params.get("stagger_ms", 100)
            warhead_type = params.get("warhead_type")
            guidance_mode = params.get("guidance_mode")
            return self.launch_salvo(
                target=target_id, count=count, munition_type=munition_type,
                profile=profile, stagger_ms=stagger_ms,
                warhead_type=warhead_type, guidance_mode=guidance_mode,
            )

        elif action == "program_munition":
            return self.program_munition(params)

        elif action == "torpedo_status":
            return self.get_torpedo_status()

        elif action == "missile_status":
            return self.get_missile_status()

        elif action == "authorize_weapon":
            weapon_type = params.get("weapon_type")
            count = params.get("count", 1)
            profile = params.get("profile", "direct")
            return self.auto_fire_manager.authorize(weapon_type, count=count, profile=profile)

        elif action == "deauthorize_weapon":
            weapon_type = params.get("weapon_type")
            return self.auto_fire_manager.deauthorize(weapon_type)

        elif action == "cease_fire":
            return self.auto_fire_manager.cease_fire()

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
            "munition_program": self._munition_program,
            "auto_fire": self.auto_fire_manager.get_state(),
        })
        return state
