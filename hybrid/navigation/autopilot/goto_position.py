# hybrid/navigation/autopilot/goto_position.py
"""Go-to-position autopilot for set_course navigation.

Supports nav-solution profiles (aggressive / balanced / conservative)
that adjust thrust and braking safety margins. Individual params can
still override profile defaults for fine-tuning.
"""

import logging
import math
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


# -- Nav solution profiles ---------------------------------------------------

GOTO_PROFILES: Dict[str, Dict] = {
    "aggressive": {
        "max_thrust": 0.50,            # ~5G on a 10G corvette
        "brake_buffer_factor": 1.1,
        "description": "5G combat burn. Fast but crew-punishing.",
        "risk_level": "high",
    },
    "balanced": {
        "max_thrust": 0.30,            # ~3G — standard military transit
        "brake_buffer_factor": 1.2,
        "description": "3G military transit. Moderate crew fatigue.",
        "risk_level": "medium",
    },
    "conservative": {
        "max_thrust": 0.10,            # ~1G — comfortable cruise
        "brake_buffer_factor": 1.3,
        "description": "1G cruise. No crew strain, fuel-efficient.",
        "risk_level": "low",
    },
}


class GoToPositionAutopilot(BaseAutopilot):
    """Autopilot that flies to a fixed position and optionally stops there."""

    PROFILES = GOTO_PROFILES

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
                - profile: "aggressive"|"balanced"|"conservative" (default "balanced")
                - x, y, z: Target coordinates
                - destination: Optional dict {x, y, z}
                - stop: Whether to stop at target (bool, default True)
                - tolerance: Distance tolerance for arrival (m, default 50.0)
                - max_thrust: Maximum thrust fraction (0..1, overrides profile)
                - coast_speed: Speed threshold to coast (m/s, default 50.0)
                - max_speed: Optional max closing speed for non-stop courses
                - brake_buffer: Extra distance before braking (m, overrides profile)
                - arrival_speed_tolerance: Speed tolerance to consider stopped (m/s, default 0.5)
        """
        super().__init__(ship, target_id, params or {})

        # Resolve profile
        self.profile_name: str = self.params.get("profile", "balanced")
        profile = dict(self.PROFILES.get(self.profile_name, self.PROFILES["balanced"]))

        destination = self.params.get("destination") or {
            "x": self.params.get("x"),
            "y": self.params.get("y"),
            "z": self.params.get("z"),
        }

        self.target_position = destination
        self.stop_at_target = bool(self.params.get("stop", True))
        self.tolerance = float(self.params.get("tolerance", 50.0))
        self.max_thrust = float(self.params.get(
            "max_thrust", profile["max_thrust"]))
        self.coast_speed = float(self.params.get("coast_speed", 50.0))
        self.max_speed = self.params.get("max_speed")

        # brake_buffer: if explicitly provided use that, otherwise derive
        # from profile factor * tolerance for a proportional margin.
        if "brake_buffer" in self.params and self.params["brake_buffer"] is not None:
            self.brake_buffer = float(self.params["brake_buffer"])
        else:
            self.brake_buffer = self.tolerance * profile["brake_buffer_factor"]

        self.arrival_speed_tolerance = float(
            self.params.get("arrival_speed_tolerance", 0.5))

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

    def _get_effective_accel(self) -> float:
        """Profile-limited acceleration for braking calculations."""
        return self._get_max_accel() * self.max_thrust

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

        max_accel = self._get_effective_accel()
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
        """Get autopilot state including profile information."""
        state = super().get_state()
        vector_to_target = subtract_vectors(self.target_position, self.ship.position)
        distance = magnitude(vector_to_target)
        direction_to_target = normalize_vector(vector_to_target)
        closing_speed = dot_product(self.ship.velocity, direction_to_target)
        max_accel = self._get_effective_accel()
        braking_distance = (closing_speed ** 2) / (2 * max_accel) if closing_speed > 0 else 0.0

        # ETA estimate
        time_to_arrival = None
        if closing_speed > 0.1:
            time_to_arrival = distance / closing_speed
        elif max_accel > 0 and distance > 0 and self.phase == self.PHASE_ACCELERATE:
            # Rough brachistochrone estimate: t = 2 * sqrt(d / a)
            time_to_arrival = 2.0 * math.sqrt(distance / max_accel)

        # Also expose as "range" for consistent field naming across autopilots
        state.update({
            "phase": self.phase,
            "profile": self.profile_name,
            "destination": self.target_position,
            "distance": distance,
            "range": distance,
            "closing_speed": closing_speed,
            "braking_distance": braking_distance,
            "time_to_arrival": time_to_arrival,
            "stop": self.stop_at_target,
            "tolerance": self.tolerance,
            "complete": self.completed,
            "status_text": self._build_status_text(distance, closing_speed, time_to_arrival),
        })
        return state

    def _build_status_text(self, distance: float, closing_speed: float,
                           eta: float = None) -> str:
        """Human-readable status for the GUI."""
        range_str = f"{distance / 1000:.1f}km" if distance >= 1000 else f"{distance:.0f}m"
        eta_str = ""
        if eta is not None:
            if eta < 60:
                eta_str = f", ETA {eta:.0f}s"
            else:
                minutes = int(eta) // 60
                secs = int(eta) % 60
                eta_str = f", ETA {minutes}m {secs:02d}s"

        if self.phase == self.PHASE_ACCELERATE:
            return f"Accelerating -- {range_str}{eta_str}"
        elif self.phase == self.PHASE_COAST:
            return f"Coasting -- {range_str}, {closing_speed:.1f} m/s{eta_str}"
        elif self.phase == self.PHASE_BRAKE:
            return f"Braking -- {range_str} remaining{eta_str}"
        elif self.phase == self.PHASE_HOLD:
            return f"Holding position at destination"
        return f"En route -- {range_str}"
