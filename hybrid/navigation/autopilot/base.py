# hybrid/navigation/autopilot/base.py
"""Base autopilot class."""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class BaseAutopilot(ABC):
    """Abstract base class for all autopilot programs."""

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize autopilot.

        Args:
            ship: Ship under autopilot control
            target_id: Target contact ID (if applicable)
            params: Additional parameters
        """
        self.ship = ship
        self.target_id = target_id
        self.params = params or {}
        self.status = "initializing"
        self.error_message = None
        self._target_warned = False

    @abstractmethod
    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust command for this tick.

        Args:
            dt: Time delta
            sim_time: Current simulation time

        Returns:
            dict: Command with {thrust, heading} or None
        """
        pass

    def get_target(self):
        """Get target ship or contact.

        Resolves target by:
        1. Sensor contact (by stable ID like C001 or original ship ID)
        2. Direct ship lookup in _all_ships_ref (fallback for raw ship IDs)

        Returns:
            Target object or None
        """
        if not self.target_id:
            return None

        # Try sensor contacts first (handles both C001 and target_station via id_mapping)
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            contact = sensors.get_contact(self.target_id)
            if contact:
                self._target_warned = False
                return contact

        # Fallback: look up directly in all_ships (handles raw ship IDs like target_station)
        all_ships = getattr(self.ship, "_all_ships_ref", [])

        # If target_id is a stable contact ID (e.g. C001), resolve to the
        # original ship ID via the contact tracker's id_mapping so the
        # all_ships fallback can match.
        lookup_ids = {self.target_id}
        if sensors and hasattr(sensors, "contact_tracker"):
            tracker = sensors.contact_tracker
            # Reverse lookup: stable_id -> real_ship_id
            for real_id, stable_id in tracker.id_mapping.items():
                if stable_id == self.target_id:
                    lookup_ids.add(real_id)
            # Forward lookup: real_ship_id -> stable_id (in case target_id is a real id)
            mapped = tracker.id_mapping.get(self.target_id)
            if mapped:
                lookup_ids.add(mapped)

        for ship in all_ships:
            if getattr(ship, "id", None) in lookup_ids:
                if not self._target_warned:
                    logger.info(f"Autopilot: target '{self.target_id}' found via direct ship lookup (not in sensor contacts)")
                    self._target_warned = True
                return ship

        if not self._target_warned:
            logger.warning(f"Autopilot: target '{self.target_id}' not found in sensors or ships")
            self._target_warned = True
        return None

    def get_state(self) -> Dict:
        """Get autopilot state.

        Returns:
            dict: Current state
        """
        return {
            "status": self.status,
            "target_id": self.target_id,
            "error": self.error_message
        }

    def _clamp_thrust(self, thrust: float) -> float:
        """Clamp thrust to valid range [0, 1].

        Args:
            thrust: Thrust value

        Returns:
            float: Clamped thrust
        """
        return max(0.0, min(1.0, thrust))

    def _normalize_angle(self, angle: float) -> float:
        """Normalize angle to [-180, 180].

        Args:
            angle: Angle in degrees

        Returns:
            float: Normalized angle
        """
        while angle > 180:
            angle -= 360
        while angle < -180:
            angle += 360
        return angle
