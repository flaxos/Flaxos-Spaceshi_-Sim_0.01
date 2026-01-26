# hybrid/navigation/autopilot/goto_position.py
"""Go-to-position autopilot for set_course navigation."""

import logging
from typing import Dict, Optional

from hybrid.navigation.autopilot.base import BaseAutopilot
from hybrid.navigation.relative_motion import vector_to_heading
from hybrid.utils.math_utils import (
    subtract_vectors,
    magnitude,
    normalize_vector,
    dot_product,
)

logger = logging.getLogger(__name__)


class GoToPositionAutopilot(BaseAutopilot):
    """Autopilot that flies to a fixed position and optionally stops there."""

    PHASE_ACCELERATE = "ACCELERATE"
    PHASE_COAST = "COAST"
    PHASE_BRAKE = "BRAKE"
    PHASE_HOLD = "HOLD"

    def __init__(self, ship, target_id: Optional[str] = None, params: Dict = None):
        """Initialize go-to-position autopilot.

        Args:
            ship: Ship under control
            target_id: Unused (fixed position target)
            params: Additional parameters:
                - x, y, z: Target coordinates
                - destination: Optional dict {x, y, z}
                - stop: Whether to stop at target (bool, default True)
                - tolerance: Distance tolerance for arrival (m, default 50.0)
                - max_thrust: Maximum thrust fraction (0..1, default 1.0)
                - coast_speed: Speed threshold to coast (m/s, default 50.0)
                - max_speed: Optional max closing speed for non-stop courses
                - brake_buffer: Extra distance before braking (m, default tolerance)
                - arrival_speed_tolerance: Speed tolerance to consider stopped (m/s, default 0.5)
        """
        super().__init__(ship, target_id, params or {})

        destination = self.params.get("destination") or {
            "x": self.params.get("x"),
            "y": self.params.get("y"),
            "z": self.params.get("z"),
        }

        self.target_position = destination
        self.stop_at_target = bool(self.params.get("stop", True))
        self.tolerance = float(self.params.get("tolerance", 50.0))
        self.max_thrust = float(self.params.get("max_thrust", 1.0))
        self.coast_speed = float(self.params.get("coast_speed", 50.0))
        self.max_speed = self.params.get("max_speed")
        self.brake_buffer = float(self.params.get("brake_buffer", self.tolerance))
        self.arrival_speed_tolerance = float(self.params.get("arrival_speed_tolerance", 0.5))

        self.phase = self.PHASE_ACCELERATE
        self.completed = False
        self.status = "active"

        if not self._destination_is_valid():
            self.status = "error"
            self.error_message = "No destination specified for set_course"

    def _destination_is_valid(self) -> bool:
        return all(
            key in self.target_position and self.target_position[key] is not None
            for key in ("x", "y", "z")
        )

    def _get_max_accel(self) -> float:
        propulsion = self.ship.systems.get("propulsion")
        if propulsion and hasattr(propulsion, "max_thrust") and self.ship.mass > 0:
            return max(propulsion.max_thrust / self.ship.mass, 0.01)
        return 0.01

    def compute(self, dt: float, sim_time: float) -> Optional[Dict]:
        """Compute thrust/heading command for go-to-position."""
        if self.status == "error":
            return None

        vector_to_target = subtract_vectors(self.target_position, self.ship.position)
        distance = magnitude(vector_to_target)
        speed = magnitude(self.ship.velocity)

        if distance <= self.tolerance:
            if self.stop_at_target:
                if speed <= self.arrival_speed_tolerance:
                    self.phase = self.PHASE_HOLD
                    self.status = "holding"
                    self.completed = True
                    return {"thrust": 0.0, "heading": self.ship.orientation}

                self.phase = self.PHASE_BRAKE
                self.status = "braking"
                return self._compute_brake_command(speed)

            self.phase = self.PHASE_COAST
            self.status = "coasting"
            self.completed = True
            return {"thrust": 0.0, "heading": vector_to_heading(vector_to_target)}

        direction_to_target = normalize_vector(vector_to_target)
        closing_speed = dot_product(self.ship.velocity, direction_to_target)

        max_accel = self._get_max_accel()
        braking_distance = (closing_speed ** 2) / (2 * max_accel) if closing_speed > 0 else 0.0

        if self.stop_at_target and closing_speed > 0:
            if distance <= braking_distance + self.brake_buffer:
                self.phase = self.PHASE_BRAKE
                self.status = "braking"
                return self._compute_brake_command(speed)

        if self.stop_at_target:
            if closing_speed >= self.coast_speed and distance > braking_distance + self.brake_buffer:
                self.phase = self.PHASE_COAST
                self.status = "coasting"
                return {"thrust": 0.0, "heading": vector_to_heading(vector_to_target)}

            self.phase = self.PHASE_ACCELERATE
            self.status = "accelerating"
            return {
                "thrust": self._clamp_thrust(self.max_thrust),
                "heading": vector_to_heading(vector_to_target),
            }

        if self.max_speed is not None and closing_speed >= float(self.max_speed):
            self.phase = self.PHASE_COAST
            self.status = "coasting"
            return {"thrust": 0.0, "heading": vector_to_heading(vector_to_target)}

        self.phase = self.PHASE_ACCELERATE
        self.status = "accelerating"
        return {
            "thrust": self._clamp_thrust(self.max_thrust),
            "heading": vector_to_heading(vector_to_target),
        }

    def _compute_brake_command(self, speed: float) -> Dict:
        if speed < 0.01:
            return {"thrust": 0.0, "heading": self.ship.orientation}

        brake_vector = {
            "x": -self.ship.velocity["x"],
            "y": -self.ship.velocity["y"],
            "z": -self.ship.velocity["z"],
        }
        desired_heading = vector_to_heading(brake_vector)
        return {
            "thrust": self._clamp_thrust(self.max_thrust),
            "heading": desired_heading,
        }

    def get_state(self) -> Dict:
        state = super().get_state()
        vector_to_target = subtract_vectors(self.target_position, self.ship.position)
        distance = magnitude(vector_to_target)
        direction_to_target = normalize_vector(vector_to_target)
        closing_speed = dot_product(self.ship.velocity, direction_to_target)
        max_accel = self._get_max_accel()
        braking_distance = (closing_speed ** 2) / (2 * max_accel) if closing_speed > 0 else 0.0

        state.update({
            "phase": self.phase,
            "destination": self.target_position,
            "distance": distance,
            "closing_speed": closing_speed,
            "braking_distance": braking_distance,
            "stop": self.stop_at_target,
            "tolerance": self.tolerance,
            "complete": self.completed,
        })
        return state
