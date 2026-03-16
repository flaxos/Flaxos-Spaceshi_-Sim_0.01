# hybrid/systems/targeting/targeting_system.py
"""Targeting system for weapon fire control and navigation.

Sprint C: Enhanced targeting with firing solution pipeline.
Implements: contact -> lock -> firing solution workflow.
"""

import logging
from enum import Enum
from typing import Dict, Optional, List
from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict
from hybrid.navigation.relative_motion import calculate_relative_motion

logger = logging.getLogger(__name__)


class LockState(Enum):
    """Target lock state progression.

    Follows the design spec targeting pipeline:
        contact -> track -> lock -> firing solution -> fire

    States:
        NONE: No target designated.
        CONTACT: Target detected by sensors, not yet being tracked.
        TRACKING: Actively building a track on the target. Track quality
            degrades with range and target acceleration.
        ACQUIRING: Lock acquisition in progress (refining track to lock).
        LOCKED: Full lock achieved, firing solutions available.
        LOST: Lock was held but has been lost; system will attempt reacquisition.
    """
    NONE = "none"
    CONTACT = "contact"
    TRACKING = "tracking"
    ACQUIRING = "acquiring"
    LOCKED = "locked"
    LOST = "lost"


class TargetingSystem(BaseSystem):
    """Targeting system for lock-on and fire control.

    Implements the targeting pipeline:
    1. Contact detection (from sensors)
    2. Lock acquisition (designate target)
    3. Firing solution (lead calculation per weapon)
    """

    def __init__(self, config: dict):
        """Initialize targeting system.

        Args:
            config: Configuration dict with:
                - lock_time: Seconds to acquire lock (default 1.0)
                - lock_range: Max range for lock (default 100000m)
        """
        super().__init__(config)

        # Lock parameters
        self.lock_acquisition_time = config.get("lock_time", 1.0)
        self.max_lock_range = config.get("lock_range", 100000.0)

        # Current target state
        self.locked_target: Optional[str] = None  # Contact ID of locked target
        self.lock_state: LockState = LockState.NONE
        self.lock_time: float = 0.0  # Time target was locked
        self.lock_progress: float = 0.0  # 0-1 progress to full lock
        self.lock_quality: float = 0.0  # Lock quality (0-1)
        self.is_firing: bool = False  # Firing state
        self.target_subsystem: Optional[str] = None  # Selected subsystem to target

        # Track quality (design spec: degrades with range and target acceleration)
        self.track_quality: float = 0.0  # 0-1 quality of the track
        self.track_time: float = 0.0  # Time spent tracking this target
        self.track_min_quality_for_lock: float = config.get("track_min_quality", 0.6)

        # Target tracking data
        self.target_data: Dict = {}  # Cached target position/velocity
        self.firing_solutions: Dict[str, dict] = {}  # weapon_id -> solution

        # Sensor damage tracking
        self._sensor_factor = 1.0
        self._target_is_drifting = False

        # Ship reference for tick
        self._ship_ref = None
        self._sim_time = 0.0

    def tick(self, dt: float, ship, event_bus):
        """Update targeting system.

        Args:
            dt: Time delta
            ship: Ship with this targeting system
            event_bus: Event bus
        """
        if not self.enabled:
            return

        self._ship_ref = ship
        self._sim_time = getattr(ship, 'sim_time', self._sim_time + dt)

        # Get sensor degradation (includes cascade effects like reactor failure)
        if hasattr(ship, 'get_effective_factor'):
            self._sensor_factor = ship.get_effective_factor("sensors")
        elif hasattr(ship, 'damage_model'):
            self._sensor_factor = ship.damage_model.get_degradation_factor("sensors")
        else:
            self._sensor_factor = 1.0

        # Get targeting cascade factor (RCS offline = can't aim, sensors offline = blind)
        if hasattr(ship, 'get_effective_factor'):
            self._targeting_factor = ship.get_effective_factor("targeting")
        else:
            self._targeting_factor = 1.0

        # Cascade: if targeting factor is zero, force-degrade all locks
        if self._targeting_factor <= 0.0:
            if self.lock_state not in (LockState.NONE, LockState.LOST):
                self._degrade_lock(dt, "cascade_denial")
            return

        # Update lock based on current state
        if self.locked_target:
            self._update_lock(dt, ship, event_bus)

    def _update_lock(self, dt: float, ship, event_bus) -> None:
        """Update lock state for current target.

        Implements the targeting pipeline:
            contact -> track -> lock -> firing solution -> fire

        Track quality degrades with range and target acceleration per design spec.
        Sensor damage degrades all targeting stages.

        Args:
            dt: Time delta in seconds.
            ship: Ship with this targeting system.
            event_bus: Event bus for publishing events.
        """
        sensors = ship.systems.get("sensors")
        if not sensors:
            self._degrade_lock(dt, "no_sensors")
            return

        contact = sensors.get_contact(self.locked_target)
        if not contact:
            self._degrade_lock(dt, "contact_lost")
            return

        # Update target data from contact
        prev_velocity = self.target_data.get("velocity", {"x": 0, "y": 0, "z": 0})
        self.target_data = {
            "position": getattr(contact, 'position', {}),
            "velocity": getattr(contact, 'velocity', {"x": 0, "y": 0, "z": 0}),
            "confidence": getattr(contact, 'confidence', 0.5),
            "last_update": self._sim_time,
        }

        # Calculate range
        rel_motion = calculate_relative_motion(ship, contact)
        range_to_target = rel_motion["range"]

        # Range check
        if range_to_target > self.max_lock_range:
            self._degrade_lock(dt, "out_of_range")
            return

        # --- Track quality calculation (design spec) ---
        # Track quality degrades with range and target acceleration.
        # Sensor damage degrades everything.
        target_vel = self.target_data["velocity"]
        accel_x = (target_vel.get("x", 0) - prev_velocity.get("x", 0)) / max(dt, 0.001)
        accel_y = (target_vel.get("y", 0) - prev_velocity.get("y", 0)) / max(dt, 0.001)
        accel_z = (target_vel.get("z", 0) - prev_velocity.get("z", 0)) / max(dt, 0.001)
        target_accel_magnitude = (accel_x**2 + accel_y**2 + accel_z**2) ** 0.5

        # Range penalty: quality drops linearly from 1.0 at 0m to 0.2 at max_lock_range
        range_factor = max(0.2, 1.0 - 0.8 * (range_to_target / self.max_lock_range))

        # Store target acceleration for firing solution confidence
        self._last_target_accel = {"x": accel_x, "y": accel_y, "z": accel_z}

        # Acceleration penalty: high-G maneuvers degrade track
        # 10 m/s^2 (~1G) = no penalty, 100 m/s^2 (~10G) = 50% penalty
        accel_factor = max(0.3, 1.0 - target_accel_magnitude / 200.0)

        # Drift predictability bonus: constant-velocity targets are easy to
        # compute firing solutions against. No acceleration means perfect
        # trajectory extrapolation — the fundamental tactical cost of drifting.
        # Bonus builds up over ~5s of continuous drift (track_time weighted).
        is_target_drifting = target_accel_magnitude < 0.5  # Near-zero accel
        if is_target_drifting and self.track_time > 2.0:
            # Up to 20% quality bonus for drifting targets
            drift_seconds = min(self.track_time, 10.0)
            predictability_bonus = 0.2 * min(1.0, (drift_seconds - 2.0) / 5.0)
            accel_factor = min(1.0, accel_factor + predictability_bonus)
        self._target_is_drifting = is_target_drifting

        # ECM penalty: target's ECM degrades our tracking pipeline
        ecm_factor = self._get_target_ecm_factor(ship, range_to_target)

        # Sensor damage penalty
        ideal_track_quality = range_factor * accel_factor * self._sensor_factor * ecm_factor
        ideal_track_quality *= self.target_data["confidence"]

        # Smooth track quality toward ideal (builds up over time)
        self.track_quality = self.track_quality * 0.85 + ideal_track_quality * 0.15
        self.track_time += dt

        # Store track quality in target data for firing solution confidence
        self.target_data["track_quality"] = self.track_quality

        # Update lock state
        if self.lock_state == LockState.TRACKING:
            # Build track quality; promote to ACQUIRING once sufficient
            if self.track_quality >= self.track_min_quality_for_lock:
                self.lock_state = LockState.ACQUIRING
                self.lock_progress = 0.0
                logger.info(
                    f"Track quality sufficient ({self.track_quality:.2f}), "
                    f"acquiring lock on {self.locked_target}"
                )
                event_bus.publish("target_track_established", {
                    "ship_id": ship.id,
                    "target_id": self.locked_target,
                    "track_quality": self.track_quality,
                    "range": range_to_target,
                })

        elif self.lock_state == LockState.ACQUIRING:
            # If track quality drops below threshold, revert to TRACKING
            if self.track_quality < self.track_min_quality_for_lock * 0.8:
                self.lock_state = LockState.TRACKING
                self.lock_progress = 0.0
                logger.info(
                    f"Track quality degraded ({self.track_quality:.2f}), "
                    f"reverting to tracking on {self.locked_target}"
                )
                return

            # Progress lock acquisition
            lock_rate = 1.0 / self.lock_acquisition_time
            lock_rate *= self._sensor_factor  # Degraded sensors lock slower
            lock_rate *= self._targeting_factor  # Cascade penalties (RCS/reactor)
            self.lock_progress = min(1.0, self.lock_progress + lock_rate * dt)

            if self.lock_progress >= 1.0:
                self.lock_state = LockState.LOCKED
                self.lock_quality = self._sensor_factor * self.target_data["confidence"]
                logger.info(f"Target lock acquired: {self.locked_target}")
                event_bus.publish("target_locked", {
                    "ship_id": ship.id,
                    "target_id": self.locked_target,
                    "range": range_to_target,
                })

        elif self.lock_state == LockState.LOCKED:
            # Maintain lock quality based on sensor quality, cascade, and confidence
            target_quality = self._sensor_factor * self._targeting_factor * self.target_data["confidence"]
            # Smooth transition
            self.lock_quality = self.lock_quality * 0.9 + target_quality * 0.1

            # If track quality drops severely, lose lock
            if self.track_quality < self.track_min_quality_for_lock * 0.5:
                self.lock_state = LockState.LOST
                logger.warning(
                    f"Lock lost on {self.locked_target}: track quality degraded "
                    f"({self.track_quality:.2f})"
                )
                return

            # Update firing solutions
            self._update_firing_solutions(ship, contact, rel_motion)

        elif self.lock_state == LockState.LOST:
            # Try to reacquire - go back to TRACKING
            self.lock_state = LockState.TRACKING
            self.track_quality *= 0.5  # Partial track retention
            self.lock_progress = 0.0

    def _get_target_ecm_factor(self, ship, range_to_target: float) -> float:
        """Get combined ECM degradation from target ship.

        Queries the target's ECM system for jamming and chaff effects
        that degrade our targeting pipeline.

        Args:
            ship: Observer ship
            range_to_target: Distance to target in metres

        Returns:
            float: Combined ECM factor (0-1, lower = more degraded)
        """
        if not self.locked_target or not hasattr(ship, "_all_ships_ref"):
            return 1.0

        # Find target ship object
        target_ship = None
        for s in ship._all_ships_ref:
            if s.id == self.locked_target:
                target_ship = s
                break

        if not target_ship:
            return 1.0

        target_ecm = target_ship.systems.get("ecm")
        if not target_ecm:
            return 1.0

        factor = 1.0

        # Radar jamming degrades track quality
        if hasattr(target_ecm, "get_jammer_effect_at_range"):
            factor *= target_ecm.get_jammer_effect_at_range(range_to_target)

        # Active chaff degrades position accuracy
        if hasattr(target_ecm, "is_chaff_active") and target_ecm.is_chaff_active():
            factor *= 0.7  # Chaff reduces targeting by 30%

        # Active flares degrade IR-based tracking
        if hasattr(target_ecm, "is_flare_active") and target_ecm.is_flare_active():
            factor *= 0.8  # Flares reduce targeting by 20%

        return max(0.05, factor)

    def _degrade_lock(self, dt: float, reason: str):
        """Degrade lock when contact is lost or out of range."""
        self.lock_quality *= 0.9  # Decay
        self.lock_progress *= 0.95

        if self.lock_quality < 0.1:
            if self.lock_state == LockState.LOCKED:
                self.lock_state = LockState.LOST
                logger.warning(f"Lock lost on {self.locked_target}: {reason}")
            elif self.lock_progress < 0.1:
                self.lock_state = LockState.NONE
                logger.warning(f"Lock failed on {self.locked_target}: {reason}")

    def _update_firing_solutions(self, ship, contact, rel_motion: Dict):
        """Update firing solutions for all weapons."""
        weapons_system = ship.systems.get("weapons")
        if not weapons_system:
            return

        # Get truth weapons if available
        truth_weapons = getattr(weapons_system, 'truth_weapons', {})

        # Compute target acceleration for confidence calculation
        target_accel = self._get_target_accel()

        # Get weapon damage factor for confidence
        weapon_damage_factor = 1.0
        if hasattr(ship, 'get_effective_factor'):
            weapon_damage_factor = ship.get_effective_factor("weapons")

        for weapon_id, weapon in truth_weapons.items():
            if hasattr(weapon, 'calculate_solution'):
                solution = weapon.calculate_solution(
                    shooter_pos=ship.position,
                    shooter_vel=ship.velocity,
                    target_pos=self.target_data["position"],
                    target_vel=self.target_data["velocity"],
                    target_id=self.locked_target,
                    sim_time=self._sim_time,
                    track_quality=self.track_quality,
                    shooter_angular_vel=getattr(ship, 'angular_velocity', None),
                    weapon_damage_factor=weapon_damage_factor,
                    target_accel=target_accel,
                )
                self.firing_solutions[weapon_id] = {
                    "valid": solution.valid,
                    "ready": solution.ready_to_fire,
                    "confidence": solution.confidence,
                    "confidence_factors": solution.confidence_factors,
                    "cone_radius_m": solution.cone_radius_m,
                    "cone_angle_deg": solution.cone_angle_deg,
                    "hit_probability": solution.hit_probability,
                    "range": solution.range_to_target,
                    "time_of_flight": solution.time_of_flight,
                    "lead_angle": solution.lead_angle,
                    "reason": solution.reason,
                    "target_subsystem": self.target_subsystem,
                }

        # Also include basic solution data
        self.firing_solutions["_basic"] = {
            "valid": True,
            "range": rel_motion["range"],
            "bearing": rel_motion["bearing"],
            "range_rate": rel_motion["range_rate"],
            "closing": rel_motion["closing"],
            "time_to_cpa": rel_motion.get("time_to_closest_approach"),
            "cpa_distance": rel_motion.get("closest_approach_distance"),
            "target_subsystem": self.target_subsystem,
        }

    def _get_target_accel(self) -> Optional[Dict[str, float]]:
        """Estimate target acceleration from velocity changes.

        Returns:
            Acceleration vector {x, y, z} in m/s², or None if unavailable.
        """
        if not self.target_data:
            return None
        # The targeting system already computes acceleration in _update_lock
        # by comparing current and previous velocities. We store the most
        # recent acceleration estimate for use by firing solutions.
        return getattr(self, "_last_target_accel", None)

    def lock_target(
        self,
        contact_id: str,
        sim_time: float = None,
        target_subsystem: Optional[str] = None,
    ) -> dict:
        """Lock onto a target.

        Args:
            contact_id: Contact ID to lock
            sim_time: Current simulation time
            target_subsystem: Optional subsystem to target

        Returns:
            dict: Result
        """
        if self.is_firing:
            return error_dict(
                "CANNOT_SWITCH_TARGETS",
                "Cannot switch targets while firing"
            )

        # Check if we have a ship reference to verify contact
        if self._ship_ref:
            sensors = self._ship_ref.systems.get("sensors")
            if sensors:
                contact = sensors.get_contact(contact_id)
                if not contact:
                    return error_dict(
                        "INVALID_CONTACT",
                        f"Contact '{contact_id}' not found in sensors"
                    )

        # Begin targeting pipeline: contact -> track -> lock -> solution -> fire
        previous_target = self.locked_target
        self.locked_target = contact_id
        self.lock_time = sim_time or self._sim_time
        self.lock_state = LockState.TRACKING  # Start at tracking stage
        self.lock_progress = 0.0
        self.lock_quality = 0.0
        self.track_quality = 0.0
        self.track_time = 0.0
        self.firing_solutions = {}
        if target_subsystem is not None:
            self.target_subsystem = target_subsystem
        elif previous_target != contact_id:
            self.target_subsystem = None

        logger.info(f"Tracking target: {contact_id}")

        return success_dict(
            f"Tracking target: {contact_id}",
            target=contact_id,
            lock_state=self.lock_state.value,
            track_quality=self.track_quality,
            lock_progress=self.lock_progress
        )

    def unlock_target(self) -> dict:
        """Unlock current target.

        Returns:
            dict: Result
        """
        if self.is_firing:
            return error_dict(
                "CANNOT_UNLOCK",
                "Cannot unlock while firing"
            )

        prev_target = self.locked_target
        self.locked_target = None
        self.lock_state = LockState.NONE
        self.lock_quality = 0.0
        self.lock_progress = 0.0
        self.track_quality = 0.0
        self.track_time = 0.0
        self.target_data = {}
        self.firing_solutions = {}
        self.target_subsystem = None

        logger.info(f"Target unlocked: {prev_target}")

        return success_dict("Target unlocked", previous_target=prev_target)

    def get_target_solution(self, ship=None) -> dict:
        """Get firing solution for locked target.

        Args:
            ship: Ship object (uses cached ref if not provided)

        Returns:
            dict: Target solution with range, bearing, etc. or error
        """
        ship = ship or self._ship_ref

        if not self.locked_target:
            return error_dict("NO_TARGET", "No target locked")

        if self.lock_state != LockState.LOCKED:
            return error_dict(
                "LOCK_NOT_READY",
                f"Lock state: {self.lock_state.value}, progress: {self.lock_progress:.0%}"
            )

        # Return cached firing solutions
        basic = self.firing_solutions.get("_basic", {})

        return {
            "ok": True,
            "target_id": self.locked_target,
            "lock_state": self.lock_state.value,
            "lock_quality": self.lock_quality,
            "target_subsystem": self.target_subsystem,
            "range": basic.get("range", 0),
            "bearing": basic.get("bearing", {}),
            "range_rate": basic.get("range_rate", 0),
            "closing": basic.get("closing", False),
            "time_to_cpa": basic.get("time_to_cpa"),
            "cpa_distance": basic.get("cpa_distance"),
            "weapons": {
                k: v for k, v in self.firing_solutions.items()
                if k != "_basic"
            }
        }

    def get_weapon_solution(self, weapon_id: str) -> dict:
        """Get firing solution for a specific weapon.

        Args:
            weapon_id: Weapon mount identifier

        Returns:
            dict: Weapon-specific firing solution
        """
        if weapon_id not in self.firing_solutions:
            return error_dict(
                "NO_SOLUTION",
                f"No firing solution for weapon '{weapon_id}'"
            )

        solution = self.firing_solutions[weapon_id]
        return {
            "ok": True,
            "weapon_id": weapon_id,
            "target_id": self.locked_target,
            "target_subsystem": self.target_subsystem,
            **solution
        }

    def get_best_weapon(self) -> Optional[str]:
        """Get the weapon with the best firing solution.

        Returns:
            str: Weapon ID with highest hit probability, or None
        """
        best_weapon = None
        best_prob = 0.0

        for weapon_id, solution in self.firing_solutions.items():
            if weapon_id == "_basic":
                continue
            if solution.get("ready") and solution.get("hit_probability", 0) > best_prob:
                best_prob = solution["hit_probability"]
                best_weapon = weapon_id

        return best_weapon

    def set_target_subsystem(self, subsystem: Optional[str], ship=None) -> dict:
        """Set or clear the targeted subsystem.

        Args:
            subsystem: Subsystem name to target (None clears selection)
            ship: Optional ship for validation

        Returns:
            dict: Result
        """
        if subsystem in (None, "", "none"):
            self.target_subsystem = None
            return success_dict("Target subsystem cleared")

        ship = ship or self._ship_ref
        if ship and hasattr(ship, "damage_model"):
            if subsystem not in ship.damage_model.subsystems:
                return error_dict(
                    "INVALID_SUBSYSTEM",
                    f"Subsystem '{subsystem}' not found"
                )

        self.target_subsystem = subsystem
        return success_dict(
            f"Target subsystem set: {subsystem}",
            target_subsystem=subsystem
        )

    def command(self, action: str, params: dict):
        """Handle targeting commands.

        Args:
            action: Command action
            params: Parameters

        Returns:
            dict: Result
        """
        if action == "lock":
            contact_id = params.get("contact_id") or params.get("target")
            if not contact_id:
                return error_dict("MISSING_PARAMETER", "contact_id required")
            sim_time = params.get("sim_time", self._sim_time)
            target_subsystem = params.get("target_subsystem")
            return self.lock_target(contact_id, sim_time, target_subsystem)

        elif action == "unlock":
            return self.unlock_target()

        elif action == "get_solution":
            ship = params.get("ship") or self._ship_ref
            return self.get_target_solution(ship)

        elif action == "get_weapon_solution":
            weapon_id = params.get("weapon_id") or params.get("weapon")
            if not weapon_id:
                return error_dict("MISSING_PARAMETER", "weapon_id required")
            return self.get_weapon_solution(weapon_id)

        elif action == "best_weapon":
            best = self.get_best_weapon()
            if best:
                return success_dict(f"Best weapon: {best}", weapon_id=best)
            return error_dict("NO_READY_WEAPON", "No weapons ready to fire")

        elif action == "set_target_subsystem":
            target_subsystem = params.get("target_subsystem")
            ship = params.get("ship") or self._ship_ref
            return self.set_target_subsystem(target_subsystem, ship)

        elif action == "assess_damage":
            return self.assess_target_damage(params)

        elif action == "status":
            return self.get_state()

        return super().command(action, params)

    def assess_target_damage(self, params: dict) -> dict:
        """Assess damage state of the locked target's subsystems.

        Uses sensor quality and track quality to estimate target health.
        Accuracy degrades with poor sensors or low track quality.

        Args:
            params: Command parameters (may include all_ships for lookup)

        Returns:
            dict: Subsystem health estimates with confidence levels
        """
        if not self.locked_target:
            return error_dict("NO_TARGET", "No target locked for damage assessment")

        if self.lock_state.value not in ("locked", "tracking", "acquiring"):
            return error_dict("INSUFFICIENT_TRACK",
                              f"Lock state '{self.lock_state.value}' insufficient for damage assessment")

        sensor_factor = self._sensor_factor
        assessment_quality = min(sensor_factor, self.track_quality)

        all_ships = params.get("all_ships", {})
        target_ship = all_ships.get(self.locked_target)

        subsystems = {}
        if target_ship and hasattr(target_ship, "damage_model"):
            dm = target_ship.damage_model
            for subsys_name in dm.subsystems:
                actual_health = dm.get_combined_factor(subsys_name)
                if assessment_quality > 0.8:
                    reported_health = actual_health
                    confidence = "high"
                elif assessment_quality > 0.5:
                    reported_health = round(actual_health * 4) / 4
                    confidence = "moderate"
                elif assessment_quality > 0.2:
                    reported_health = round(actual_health * 2) / 2
                    confidence = "low"
                else:
                    reported_health = None
                    confidence = "none"

                status = "unknown"
                if reported_health is not None:
                    if reported_health > 0.75:
                        status = "nominal"
                    elif reported_health > 0.25:
                        status = "impaired"
                    elif reported_health > 0:
                        status = "critical"
                    else:
                        status = "destroyed"

                subsystems[subsys_name] = {
                    "health": reported_health,
                    "status": status,
                    "confidence": confidence,
                }
        else:
            for subsys in ["propulsion", "rcs", "sensors", "weapons", "reactor"]:
                subsystems[subsys] = {"health": None, "status": "unknown", "confidence": "none"}

        return success_dict(
            f"Damage assessment for {self.locked_target}",
            target_id=self.locked_target,
            assessment_quality=round(assessment_quality, 2),
            subsystems=subsystems,
        )

    def get_state(self) -> dict:
        """Get targeting system state.

        Returns:
            dict: State
        """
        state = super().get_state()
        state.update({
            "locked_target": self.locked_target,
            "lock_state": self.lock_state.value,
            "track_quality": self.track_quality,
            "lock_progress": self.lock_progress,
            "lock_quality": self.lock_quality,
            "is_firing": self.is_firing,
            "target_subsystem": self.target_subsystem,
            "target_is_drifting": self._target_is_drifting if self.locked_target else None,
            "target_data": self.target_data if self.locked_target else None,
            "solutions": {
                k: {
                    "valid": v.get("valid"),
                    "ready": v.get("ready"),
                    "confidence": v.get("confidence"),
                    "confidence_factors": v.get("confidence_factors"),
                    "cone_radius_m": v.get("cone_radius_m"),
                    "cone_angle_deg": v.get("cone_angle_deg"),
                    "hit_probability": v.get("hit_probability"),
                    "range": v.get("range"),
                    "time_of_flight": v.get("time_of_flight"),
                    "lead_angle": v.get("lead_angle"),
                    "reason": v.get("reason"),
                    "target_subsystem": v.get("target_subsystem"),
                }
                for k, v in self.firing_solutions.items()
                if k != "_basic"
            } if self.firing_solutions else {},
        })
        return state
