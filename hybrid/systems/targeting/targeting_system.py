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
    """Target lock state progression."""
    NONE = "none"  # No target
    CONTACT = "contact"  # Target detected, not locked
    ACQUIRING = "acquiring"  # Lock in progress
    LOCKED = "locked"  # Full lock, solution available
    LOST = "lost"  # Lock lost, reacquiring


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
        self.locked_target = None  # Contact ID of locked target
        self.lock_state = LockState.NONE
        self.lock_time = 0.0  # Time target was locked
        self.lock_progress = 0.0  # 0-1 progress to full lock
        self.lock_quality = 0.0  # Lock quality (0-1)
        self.is_firing = False  # Firing state
        self.target_subsystem = None  # Selected subsystem to target

        # Target tracking data
        self.target_data: Dict = {}  # Cached target position/velocity
        self.firing_solutions: Dict[str, dict] = {}  # weapon_id -> solution

        # Sensor damage tracking
        self._sensor_factor = 1.0

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

        # Get sensor degradation
        if hasattr(ship, 'damage_model'):
            self._sensor_factor = ship.damage_model.get_degradation_factor("sensors")
        else:
            self._sensor_factor = 1.0

        # Update lock based on current state
        if self.locked_target:
            self._update_lock(dt, ship, event_bus)

    def _update_lock(self, dt: float, ship, event_bus):
        """Update lock state for current target."""
        sensors = ship.systems.get("sensors")
        if not sensors:
            self._degrade_lock(dt, "no_sensors")
            return

        contact = sensors.get_contact(self.locked_target)
        if not contact:
            self._degrade_lock(dt, "contact_lost")
            return

        # Update target data from contact
        self.target_data = {
            "position": getattr(contact, 'position', contact.get('position', {})),
            "velocity": getattr(contact, 'velocity', contact.get('velocity', {"x": 0, "y": 0, "z": 0})),
            "confidence": getattr(contact, 'confidence', contact.get('confidence', 0.5)),
            "last_update": self._sim_time,
        }

        # Calculate range
        rel_motion = calculate_relative_motion(ship, contact)
        range_to_target = rel_motion["range"]

        # Range check
        if range_to_target > self.max_lock_range:
            self._degrade_lock(dt, "out_of_range")
            return

        # Update lock state
        if self.lock_state == LockState.ACQUIRING:
            # Progress lock acquisition
            lock_rate = 1.0 / self.lock_acquisition_time
            lock_rate *= self._sensor_factor  # Degraded sensors lock slower
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
            # Maintain lock quality based on sensor quality and target confidence
            target_quality = self._sensor_factor * self.target_data["confidence"]
            # Smooth transition
            self.lock_quality = self.lock_quality * 0.9 + target_quality * 0.1

            # Update firing solutions
            self._update_firing_solutions(ship, contact, rel_motion)

        elif self.lock_state == LockState.LOST:
            # Try to reacquire
            self.lock_state = LockState.ACQUIRING
            self.lock_progress = 0.5  # Faster reacquisition

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

        for weapon_id, weapon in truth_weapons.items():
            if hasattr(weapon, 'calculate_solution'):
                solution = weapon.calculate_solution(
                    shooter_pos=ship.position,
                    shooter_vel=ship.velocity,
                    target_pos=self.target_data["position"],
                    target_vel=self.target_data["velocity"],
                    target_id=self.locked_target,
                    sim_time=self._sim_time,
                )
                self.firing_solutions[weapon_id] = {
                    "valid": solution.valid,
                    "ready": solution.ready_to_fire,
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

        # Begin lock acquisition
        previous_target = self.locked_target
        self.locked_target = contact_id
        self.lock_time = sim_time or self._sim_time
        self.lock_state = LockState.ACQUIRING
        self.lock_progress = 0.0
        self.lock_quality = 0.0
        self.firing_solutions = {}
        if target_subsystem is not None:
            self.target_subsystem = target_subsystem
        elif previous_target != contact_id:
            self.target_subsystem = None

        logger.info(f"Acquiring lock on: {contact_id}")

        return success_dict(
            f"Acquiring lock on: {contact_id}",
            target=contact_id,
            lock_state=self.lock_state.value,
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

        elif action == "status":
            return self.get_state()

        return super().command(action, params)

    def get_state(self) -> dict:
        """Get targeting system state.

        Returns:
            dict: State
        """
        state = super().get_state()
        state.update({
            "locked_target": self.locked_target,
            "lock_state": self.lock_state.value,
            "lock_progress": self.lock_progress,
            "lock_quality": self.lock_quality,
            "is_firing": self.is_firing,
            "target_subsystem": self.target_subsystem,
            "target_data": self.target_data if self.locked_target else None,
            "solutions": {
                k: {
                    "valid": v.get("valid"),
                    "ready": v.get("ready"),
                    "hit_probability": v.get("hit_probability"),
                    "range": v.get("range"),
                    "reason": v.get("reason"),
                    "target_subsystem": v.get("target_subsystem"),
                }
                for k, v in self.firing_solutions.items()
                if k != "_basic"
            } if self.firing_solutions else {},
        })
        return state
