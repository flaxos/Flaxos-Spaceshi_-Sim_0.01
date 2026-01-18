# hybrid/navigation/autopilot/base.py
"""Base autopilot class."""

from abc import ABC, abstractmethod
from typing import Dict, Optional

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

        Returns:
            Target object or None
        """
        if not self.target_id:
            return None

        # Try to get from sensors
        sensors = self.ship.systems.get("sensors")
        if sensors and hasattr(sensors, "get_contact"):
            return sensors.get_contact(self.target_id)

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
