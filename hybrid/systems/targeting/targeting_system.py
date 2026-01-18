# hybrid/systems/targeting/targeting_system.py
"""Targeting system for weapon fire control and navigation."""

import logging
from hybrid.core.base_system import BaseSystem
from hybrid.utils.errors import success_dict, error_dict
from hybrid.navigation.relative_motion import calculate_relative_motion

logger = logging.getLogger(__name__)

class TargetingSystem(BaseSystem):
    """Targeting system for lock-on and fire control."""

    def __init__(self, config: dict):
        """Initialize targeting system.

        Args:
            config: Configuration dict
        """
        super().__init__(config)

        self.locked_target = None  # Contact ID of locked target
        self.lock_time = 0.0  # Time target was locked
        self.lock_quality = 0.0  # Lock quality (0-1)
        self.is_firing = False  # Firing state

    def tick(self, dt: float, ship, event_bus):
        """Update targeting system.

        Args:
            dt: Time delta
            ship: Ship with this targeting system
            event_bus: Event bus
        """
        if not self.enabled:
            return

        # Update lock quality based on sensor contact
        if self.locked_target:
            sensors = ship.systems.get("sensors")
            if sensors:
                contact = sensors.get_contact(self.locked_target)
                if contact:
                    # Update lock quality from contact confidence
                    self.lock_quality = getattr(contact, 'confidence', 0.5)
                else:
                    # Contact lost - degrade lock
                    self.lock_quality *= 0.95
                    if self.lock_quality < 0.1:
                        logger.warning(f"Lost lock on {self.locked_target}")
                        self.unlock_target()

    def lock_target(self, contact_id: str, sim_time: float = None) -> dict:
        """Lock onto a target.

        Args:
            contact_id: Contact ID to lock
            sim_time: Current simulation time

        Returns:
            dict: Result
        """
        if self.is_firing:
            return error_dict(
                "CANNOT_SWITCH_TARGETS",
                "Cannot switch targets while firing"
            )

        # Verify contact exists in sensors
        # This would be done via ship reference, simplified here
        self.locked_target = contact_id
        self.lock_time = sim_time or 0.0
        self.lock_quality = 1.0

        logger.info(f"Target locked: {contact_id}")

        return success_dict(
            f"Target locked: {contact_id}",
            target=contact_id,
            lock_quality=self.lock_quality
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
        self.lock_quality = 0.0

        logger.info(f"Target unlocked: {prev_target}")

        return success_dict("Target unlocked")

    def get_target_solution(self, ship) -> dict:
        """Get firing solution for locked target.

        Args:
            ship: Ship object

        Returns:
            dict: Target solution with range, bearing, etc. or error
        """
        if not self.locked_target:
            return error_dict("NO_TARGET", "No target locked")

        # Get target from sensors
        sensors = ship.systems.get("sensors")
        if not sensors:
            return error_dict("NO_SENSORS", "Sensor system not available")

        contact = sensors.get_contact(self.locked_target)
        if not contact:
            return error_dict(
                "TARGET_LOST",
                f"Target {self.locked_target} not in sensor contacts"
            )

        # Calculate firing solution
        rel_motion = calculate_relative_motion(ship, contact)

        return {
            "ok": True,
            "target_id": self.locked_target,
            "range": rel_motion["range"],
            "bearing": rel_motion["bearing"],
            "range_rate": rel_motion["range_rate"],
            "closing": rel_motion["closing"],
            "lock_quality": self.lock_quality,
            "time_to_cpa": rel_motion.get("time_to_closest_approach"),
            "cpa_distance": rel_motion.get("closest_approach_distance")
        }

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
            sim_time = params.get("sim_time", 0.0)
            return self.lock_target(contact_id, sim_time)

        elif action == "unlock":
            return self.unlock_target()

        elif action == "get_solution":
            ship = params.get("ship")
            if not ship:
                return error_dict("MISSING_PARAMETER", "ship reference required")
            return self.get_target_solution(ship)

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
            "lock_quality": self.lock_quality,
            "is_firing": self.is_firing
        })
        return state
