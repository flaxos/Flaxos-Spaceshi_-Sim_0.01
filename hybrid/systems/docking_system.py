# hybrid/systems/docking_system.py
"""Docking system implementation for proximity-based docking."""

import logging

from hybrid.core.base_system import BaseSystem
from hybrid.navigation.relative_motion import calculate_relative_motion

logger = logging.getLogger(__name__)


class DockingSystem(BaseSystem):
    """Tracks docking requests and validates docking conditions."""

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        self.docking_range = float(config.get("docking_range", config.get("max_range", 50.0)))
        self.max_relative_velocity = float(
            config.get("max_relative_velocity", config.get("docking_velocity", 1.0))
        )

        self.target_id = None
        self.target_ship = None
        self.status = "idle"
        self.last_check = {}

    def tick(self, dt, ship=None, event_bus=None):
        """Evaluate docking criteria each tick when a request is active."""
        if not self.enabled:
            self.status = "offline"
            return

        if not ship:
            self.status = "idle"
            return

        if getattr(ship, "docked_to", None):
            self.status = "docked"
            return

        if not self.target_ship and not self.target_id:
            self.status = "idle"
            return

        target_ship = self.target_ship
        target_id = self.target_id
        if not target_ship:
            self.status = "target_lost"
            return

        rel_motion = calculate_relative_motion(ship, target_ship)
        relative_speed = rel_motion.get("relative_velocity_magnitude", 0.0)
        range_to_target = rel_motion.get("range", 0.0)
        self.last_check = {
            "range": range_to_target,
            "relative_velocity": relative_speed,
        }

        if range_to_target <= self.docking_range and relative_speed <= self.max_relative_velocity:
            ship.docked_to = target_id or getattr(target_ship, "id", None)
            self.status = "docked"
            if event_bus:
                event_bus.publish(
                    "docked",
                    {
                        "ship": ship.id,
                        "target": ship.docked_to,
                        "range": range_to_target,
                        "relative_velocity": relative_speed,
                    },
                )
            logger.info("Ship %s docked with %s", ship.id, ship.docked_to)
        else:
            self.status = "approaching"

    def command(self, action, params):
        """Handle docking commands."""
        if action == "request_docking":
            return self._cmd_request_docking(params)
        if action == "cancel_docking":
            return self._cmd_cancel_docking()
        if action == "status":
            return self.get_state()
        if action == "power_on":
            return self.power_on()
        if action == "power_off":
            return self.power_off()
        return super().command(action, params)

    def _cmd_request_docking(self, params):
        if not self.enabled:
            return {"error": "Docking system is disabled"}

        ship = params.get("_ship") or params.get("ship")
        if ship and getattr(ship, "docked_to", None):
            return {"error": f"Ship already docked to {ship.docked_to}"}

        target_ship = params.get("target_ship")
        target_id = params.get("target_id") or params.get("target")
        if target_ship and not target_id:
            target_id = getattr(target_ship, "id", None)
        if not target_ship and hasattr(target_id, "id"):
            target_ship = target_id
            target_id = getattr(target_ship, "id", None)
        if not target_ship:
            all_ships = params.get("all_ships")
            if isinstance(all_ships, dict):
                target_ship = all_ships.get(target_id)
            elif all_ships:
                for candidate in all_ships:
                    if getattr(candidate, "id", None) == target_id:
                        target_ship = candidate
                        break

        if ship and target_id == ship.id:
            return {"error": "Cannot dock with self"}

        if not target_id:
            return {"error": "Missing target for docking"}

        self.target_id = target_id
        self.target_ship = target_ship
        self.status = "docking_initiated"

        event_bus = params.get("event_bus")
        if event_bus and ship:
            event_bus.publish(
                "docking_initiated",
                {
                    "ship": ship.id,
                    "target": target_id,
                    "range": self.last_check.get("range"),
                    "relative_velocity": self.last_check.get("relative_velocity"),
                },
            )

        return {
            "status": "docking_requested",
            "target": target_id,
            "docking_range": self.docking_range,
            "max_relative_velocity": self.max_relative_velocity,
        }

    def _cmd_cancel_docking(self):
        self.target_id = None
        self.target_ship = None
        self.status = "idle"
        return {"status": "docking_cancelled"}

    def get_state(self):
        return {
            **super().get_state(),
            "status": self.status,
            "target": self.target_id,
            "docking_range": self.docking_range,
            "max_relative_velocity": self.max_relative_velocity,
            "last_check": self.last_check,
        }
